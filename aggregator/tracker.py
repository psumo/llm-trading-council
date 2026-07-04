"""Paper-trading position tracker -- orchestrates open/monitor/close.

Wires together the store (SQLite), price fetcher (Binance + fallback), the pure
close-rule logic (tracker_models), stats (tracker_stats), event logging and
toasts. One open position at a time is enforced as an invariant.

Open rule:
  Judge direction LONG/SHORT, status ok, conviction >= min_conviction, with a
  non-null entry AND stop_loss -> open a position (if none is open).

Each poll tick (on_tick) updates the open position's excursion and evaluates
the close rules against the freshly fetched price.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from config import GuardsCfg, TrackerCfg
from guards import (
    CooldownAfterLossesGuard,
    DailyLossStopGuard,
    GuardContext,
    Guard,
    MaxConcurrentGuard,
    MinStopDistanceGuard,
    QuorumGuard,
    run_guards,
)
from judge import JudgeResult
from paper_account import PaperAccount
from persistence import EventLog
from sources.base import Vote
from tracker_models import (
    Position,
    decide_close,
    realized_close,
    unrealized_r,
)
from tracker_context import build_context
from tracker_price import PriceFetcher, PriceResult
from tracker_stats import compute_stats

# Live price within this fraction of the judge entry -> treat them as equal and
# use the judge's entry as the fill (avoids cosmetic micro-differences).
_ENTRY_MATCH_TOLERANCE = 0.0015  # 0.15%


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Re-log an identical (symbol, direction, reasons) block at most this often.
_BLOCK_RELOG_SECONDS = 600.0  # 10 minutes


def _build_guards(cfg: GuardsCfg) -> list[Guard]:
    """Construct the ordered guard chain from config thresholds."""
    return [
        QuorumGuard(min_agree=cfg.min_agree),
        MinStopDistanceGuard(min_pct=cfg.min_stop_pct),
        CooldownAfterLossesGuard(
            consecutive=cfg.cooldown_losses,
            cooldown_minutes=cfg.cooldown_minutes,
        ),
        DailyLossStopGuard(max_daily_loss_r=cfg.max_daily_loss_r),
        MaxConcurrentGuard(max_open=cfg.max_concurrent),
    ]


class Tracker:
    """Per-symbol position lifecycle over a shared global paper account.

    The one-open-position invariant is PER SYMBOL: this tracker only ever holds
    one position for its own `symbol`. Risk is sized off, and realized PnL flows
    into, the shared `PaperAccount` (one global balance / equity curve).
    """

    def __init__(
        self,
        cfg: TrackerCfg,
        symbol: str,
        account: PaperAccount,
        events: EventLog,
        notify: Callable[[str, str], bool],
        guards_cfg: GuardsCfg | None = None,
    ):
        self.cfg = cfg
        self.symbol = symbol
        self.account = account
        self.store = account.store
        self.events = events
        self._notify = notify
        # Default to an all-default (enabled) guard config when not supplied, so
        # existing call sites/tests keep working; instrument.py passes cfg.guards.
        self.guards_cfg = guards_cfg if guards_cfg is not None else GuardsCfg()  # type: ignore[call-arg]
        self._guards: list[Guard] = _build_guards(self.guards_cfg)
        # Last block surfaced for this symbol (for the dashboard) + throttle key.
        self.last_block: dict[str, Any] | None = None
        self._last_block_key: tuple[str, str, tuple[str, ...]] | None = None
        self._last_block_ts: float = 0.0
        self.price = PriceFetcher(
            symbol=symbol,
            timeout=cfg.price_timeout_seconds,
            enabled=cfg.price_poll,
        )
        self.open_position: Position | None = (
            self.store.load_open_position_for_symbol(symbol)
        )
        self.last_price_status: str = "starting"
        self.last_price_source: str = "none"
        self.last_price: float | None = None
        # Wall-clock ts of the previous NON-STALE tick, used to advance the
        # open position's live-market hold time. None until the first such tick.
        self._last_live_tick_ts: float | None = None

    @property
    def balance(self) -> float:
        """The shared global balance (read-through to the paper account)."""
        return self.account.balance

    # ---- open ----------------------------------------------------------

    @property
    def is_busted(self) -> bool:
        """Account is busted when the global balance has hit zero. No further
        positions may be opened (a zero balance sizes a zero-unit position)."""
        return self.account.balance <= 0.0

    def _should_open(self, judge: JudgeResult) -> bool:
        # Gate on ENTRY_CONVICTION -- the decoupled conviction-to-enter signal.
        # NOT the old conflated conviction, and NEVER flat_confidence (a
        # high-confidence FLAT must never open a trade).
        return (
            self.cfg.enabled
            and not self.is_busted
            and self.open_position is None
            and judge.status == "ok"
            and judge.direction in ("LONG", "SHORT")
            and judge.entry_conviction >= self.cfg.min_conviction
            and judge.entry is not None
            and judge.stop_loss is not None
        )

    def _confluence_size_factor(self, entry_conviction: float) -> float:
        """Fractional-Kelly-style sizing dial in [0.4, 1.0].

        Scale risk by a confluence factor so marginal setups (entry_conviction
        at the act threshold) take ~half risk and strong ones (100) take full
        risk. Linear in entry_conviction, clamped to [0.4, 1.0].
        """
        conv = max(0.0, min(100.0, entry_conviction))
        return max(0.4, min(1.0, conv / 100.0))

    def _ev_blocks(self, judge: JudgeResult) -> bool:
        """Soft expected-value gate (only when win_probability is provided).

        Require positive expected R after the judge's own numbers:
            win_probability * rr - (1 - win_probability) > 0
        Returns True (and the caller logs a POSITION_SKIP) when EV is negative.
        """
        wp = judge.win_probability
        rr = judge.risk_reward
        if wp is None or rr is None or rr <= 0:
            return False  # no EV input -> do not block
        ev_r = wp * rr - (1.0 - wp)
        return ev_r <= 0.0

    def _resolve_entry(
        self, judge_entry: float, live_price: float | None
    ) -> tuple[float, float | None]:
        """Return (entry_used, live_entry_recorded).

        If live price is within tolerance of the judge entry, use the judge's
        entry. Otherwise record both and use the live price as the fill.
        """
        if live_price is None or judge_entry <= 0:
            return judge_entry, live_price
        drift = abs(live_price - judge_entry) / judge_entry
        if drift <= _ENTRY_MATCH_TOLERANCE:
            return judge_entry, live_price
        return live_price, live_price

    def _open(self, judge: JudgeResult, votes: dict[str, Vote], price: float | None) -> None:
        assert judge.entry is not None and judge.stop_loss is not None
        entry, live_entry = self._resolve_entry(judge.entry, price)
        risk_distance = abs(entry - judge.stop_loss)
        if risk_distance <= 0:
            self.events.append(
                "POSITION_SKIP",
                {"summary": f"skip open: entry==stop ({entry})"},
            )
            return
        # Validate the levels are SELF-CONSISTENT before trusting the judge.
        # The judge's claimed risk_reward can disagree with its own entry/SL/TP
        # (observed: claimed 1.52 while TP sat 9.5pts/0.015% from entry -> real
        # R:R 0.027, a "win" that lost money after fees). Recompute R:R from the
        # actual levels, require TP on the correct side with R:R >= rr_floor, and
        # use THIS recomputed value (never the judge's claim) for the EV gate.
        tp = judge.take_profit_1
        if tp is None:
            self.events.append(
                "POSITION_SKIP",
                {"summary": "skip open: no take_profit_1", "symbol": self.symbol},
            )
            return
        is_long = judge.direction == "LONG"
        tp_correct_side = (tp > entry) if is_long else (tp < entry)
        reward_distance = abs(tp - entry)
        actual_rr = reward_distance / risk_distance if risk_distance > 0 else 0.0
        rr_floor = self.cfg.rr_floor
        if not tp_correct_side or actual_rr < rr_floor:
            self.events.append(
                "POSITION_SKIP",
                {
                    "summary": (
                        f"skip open: degenerate levels — actual R:R {actual_rr:.2f} "
                        f"< floor {rr_floor} (entry {entry}, SL {judge.stop_loss}, "
                        f"TP {tp}; judge claimed {judge.risk_reward}, "
                        f"tp_side_ok={tp_correct_side})"
                    ),
                    "symbol": self.symbol,
                },
            )
            return
        # Soft EV gate using the RECOMPUTED R:R (positive EV only when
        # wp*rr - (1-wp) > 0).
        wp = judge.win_probability
        if wp is not None:
            ev_r = wp * actual_rr - (1.0 - wp)
            if ev_r <= 0:
                self.events.append(
                    "POSITION_SKIP",
                    {
                        "summary": (
                            f"skip open: negative EV {ev_r:+.3f}R "
                            f"(win_prob {wp:.2f}, actual R:R {actual_rr:.2f})"
                        ),
                        "symbol": self.symbol,
                    },
                )
                return
        # Continuous (fractional-Kelly) sizing: scale risk by a confluence factor
        # so marginal setups take ~half risk and strong ones take full risk.
        size_factor = self._confluence_size_factor(judge.entry_conviction)
        risk_usd = self.account.risk_usd(self.cfg.risk_pct) * size_factor
        size_units = risk_usd / risk_distance if risk_distance > 0 else 0.0
        if risk_usd <= 0 or size_units <= 0:
            # Busted/zero balance -> a zero-size position is a zombie trade.
            self.events.append(
                "POSITION_SKIP",
                {"summary": f"skip open: zero size (balance ${self.balance:.2f})"},
            )
            return
        source_dirs = {k: str(v.direction) for k, v in votes.items()}
        opened_at = _now_iso()
        context = build_context(votes, judge, opened_at, entry)
        context["symbol"] = self.symbol
        pos = Position(
            id=0,  # 0 -> store allocates a fresh AUTOINCREMENT id atomically
            opened_at=opened_at,
            direction=judge.direction,
            conviction=judge.conviction,
            symbol=self.symbol,
            entry=entry,
            stop_loss=judge.stop_loss,
            take_profit_1=judge.take_profit_1,
            take_profit_2=judge.take_profit_2,
            risk_reward=judge.risk_reward,
            rationale=(judge.rationale or "")[:400],
            source_dirs=source_dirs,
            context=context,
            risk_usd=round(risk_usd, 4),
            size_units=round(size_units, 8),
            judge_entry=judge.entry,
            live_entry=live_entry,
            last_price=price,
        )
        # Allocate id + insert inside one store-lock critical section so two
        # symbols opening in the same tick can never collide on id.
        pos = self.store.open_position_atomic(pos)
        self.open_position = pos
        self.events.append(
            "POSITION_OPEN",
            {
                "summary": (
                    f"{self.symbol} {pos.direction} @ {pos.entry} SL {pos.stop_loss} "
                    f"TP1 {pos.take_profit_1} conv {pos.conviction:.0f} "
                    f"risk ${pos.risk_usd:.2f}"
                ),
                "position": pos.to_dict(),
            },
        )
        tp = f" TP {pos.take_profit_1}" if pos.take_profit_1 is not None else ""
        self._notify(
            f"{self.symbol} PAPER OPEN: {pos.direction} @ {pos.entry:g}",
            f"SL {pos.stop_loss:g}{tp} · conv {pos.conviction:.0f} · risk ${pos.risk_usd:.2f}",
        )

    # ---- monitor / close ----------------------------------------------

    def _close(self, pos: Position, exit_price: float, outcome: str) -> None:
        closed = realized_close(pos, exit_price, outcome, _now_iso())
        self.store.upsert_position(closed)
        balance = self.account.apply_pnl(closed.pnl_usd or 0.0, closed.closed_at)
        self.open_position = None
        r = closed.r_multiple or 0.0
        self.events.append(
            "POSITION_CLOSE",
            {
                "summary": (
                    f"{self.symbol} {closed.direction} {outcome.upper()} {r:+.2f}R "
                    f"@ {exit_price} · bal ${balance:.2f}"
                ),
                "position": closed.to_dict(),
            },
        )
        tag = "WIN" if r > 0 else "LOSS" if r < 0 else "FLAT"
        self._notify(
            f"{self.symbol} PAPER CLOSE: {tag} {r:+.2f}R",
            f"{closed.direction} {outcome} @ {exit_price:g} · bal ${balance:.2f}",
        )

    def _age_hours(self, pos: Position) -> float:
        try:
            opened = datetime.fromisoformat(pos.opened_at)
        except ValueError:
            return 0.0
        return max(0.0, (datetime.now(timezone.utc) - opened).total_seconds() / 3600.0)

    def on_tick(self, judge: JudgeResult, votes: dict[str, Vote]) -> None:
        """Called once per polling loop tick. Fetches price, updates the open
        position excursion, applies close rules, then maybe opens a new one.

        A price-fetch failure skips price-dependent work for this tick but never
        raises -- the status is recorded for /api/state.
        """
        if not self.cfg.enabled:
            return
        fallback_close = _orderflow_close(votes)
        result: PriceResult = self.price.get_price(fallback_close)
        self.last_price_status = result.status
        self.last_price_source = result.source
        self.last_price = result.price

        if result.price is None:
            # No usable price this tick: can't monitor or open safely. Skip.
            return
        if result.stale:
            # Frozen price (restricted-hours instrument outside its session):
            # evaluating SL/TP/timeout or opening against it would act on a
            # quote the market can't actually fill. Freeze until fresh data.
            # Crucially, do NOT advance the hold clock while frozen.
            return
        price = result.price

        # Live tick: advance the open position's live-market hold time by the
        # gap since the previous live tick (clamped to the configured max hold
        # so a long off-hours wall gap can't be misattributed as live time).
        now_ts = time.monotonic()
        delta = 0.0
        if self._last_live_tick_ts is not None:
            delta = max(0.0, now_ts - self._last_live_tick_ts)
            delta = min(delta, self.cfg.max_hold_hours * 3600.0)
        self._last_live_tick_ts = now_ts

        if self.open_position is not None:
            pos = self.open_position.with_excursion(price)
            pos = pos.with_active_time(delta)
            self.open_position = pos
            decision = decide_close(
                pos,
                price=price,
                judge_direction=judge.direction if judge.status == "ok" else "FLAT",
                judge_conviction=judge.conviction,
                min_conviction=self.cfg.min_conviction,
                age_hours=pos.active_hours,  # live-market hold, not wall age
                max_hold_hours=self.cfg.max_hold_hours,
            )
            if decision is not None:
                outcome, exit_price = decision
                self._close(pos, exit_price, outcome)
            else:
                # Persist the updated excursion + hold time so a restart keeps
                # MFE/MAE and the live-hold clock.
                self.store.update_position(pos)

        if self._should_open(judge):
            if self._guards_block(judge, votes):
                return
            self._open(judge, votes, price)

    # ---- guards --------------------------------------------------------

    def _guards_block(self, judge: JudgeResult, votes: dict[str, Vote]) -> bool:
        """Run the pre-execution guard chain. Returns True (and logs a throttled
        POSITION_BLOCKED event + records last_block) when the open is rejected.

        When guards are disabled this is a no-op that always allows.
        """
        if not self.guards_cfg.enabled:
            return False
        ctx = GuardContext(
            symbol=self.symbol,
            judge_direction=judge.direction,
            judge_conviction=judge.conviction,
            entry=judge.entry,
            stop_loss=judge.stop_loss,
            votes=votes,
            open_positions_count=self.store.count_open(),
            recent_closed=self.store.recent_closed(limit=10),
            now=datetime.now(timezone.utc),
        )
        rejections = run_guards(self._guards, ctx)
        if not rejections:
            return False
        reasons = [reason for _, reason in rejections]
        at = _now_iso()
        self.last_block = {"at": at, "reasons": reasons}
        self._log_block(judge.direction, judge.conviction, reasons)
        return True

    def _log_block(
        self, direction: str, conviction: float, reasons: list[str]
    ) -> None:
        """Append a POSITION_BLOCKED event, throttling identical repeats to at
        most once per 10 minutes (same symbol + direction + reasons)."""
        key = (self.symbol, direction, tuple(reasons))
        now_ts = time.monotonic()
        if (
            key == self._last_block_key
            and (now_ts - self._last_block_ts) < _BLOCK_RELOG_SECONDS
        ):
            return
        self._last_block_key = key
        self._last_block_ts = now_ts
        self.events.append(
            "POSITION_BLOCKED",
            {
                "summary": (
                    f"{self.symbol} {direction} BLOCKED: " + "; ".join(reasons)
                ),
                "symbol": self.symbol,
                "direction": direction,
                "conviction": conviction,
                "reasons": reasons,
            },
        )

    # ---- snapshot for /api/state --------------------------------------

    def _open_position_view(self) -> dict[str, Any] | None:
        pos = self.open_position
        if pos is None:
            return None
        d = pos.to_dict()
        if self.last_price is not None:
            d["current_price"] = self.last_price
            d["unrealized_r"] = round(unrealized_r(pos, self.last_price), 3)
        d["age_hours"] = round(self._age_hours(pos), 3)
        return d

    def snapshot(self) -> dict[str, Any]:
        """Per-symbol tracker view (for this symbol's dashboard tab).

        `stats` are computed over THIS symbol's closed trades. The global paper
        account (one balance, whole-account performance) is reported separately
        by PaperAccount-level aggregation in main.py; here `balance` is the
        shared global balance for convenience.
        """
        closed = self.store.closed_positions_for_symbol(self.symbol)
        curve = self.store.equity_curve()
        stats = compute_stats(closed, curve, self.balance, self.cfg.start_balance)
        recent = [p.to_dict() for p in closed[:10]]
        return {
            "enabled": self.cfg.enabled,
            "symbol": self.symbol,
            "busted": self.is_busted,
            "balance": round(self.balance, 2),
            "price_status": self.last_price_status,
            "price_source": self.last_price_source,
            "last_price": self.last_price,
            "stats": stats,
            "open_position": self._open_position_view(),
            "recent_closed": recent,
            "last_block": self.last_block,
        }


def _orderflow_close(votes: dict[str, Vote]) -> float | None:
    of = votes.get("orderflow")
    if of is None:
        return None
    close = of.extra.get("close")
    if isinstance(close, (int, float)) and close > 0:
        return float(close)
    return None
