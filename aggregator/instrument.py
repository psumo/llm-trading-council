"""Per-instrument engine: one symbol's sources, confluence, judge and tracker.

Each configured instrument owns its own source set (parameterised by symbol),
confluence thresholds, stateful judge (one Gemini call per symbol) and per-symbol
paper-position tracker over the SHARED global account. A single instrument's
source failure degrades only that instrument -- the aggregator loop catches per
instrument so one symbol can never take down another.

The llm_trader voice is single-pair (BTC only): an instrument whose `voices`
omit it simply never constructs that source, and its vote map carries only the
voices it runs.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from config import (
    Config,
    InstrumentCfg,
    read_orderflow_password,
)
from confluence import Confluence, evaluate
from judge import Judge, JudgeResult
from orderflow_tf import TfSummaryBuilder, summaries_to_dicts
from paper_account import PaperAccount
from persistence import EventLog
from scorecards import Scorecards
from sources.base import Vote
from sources.llm_trader import LlmTraderSource
from sources.llm_tradebot import LlmTradebotSource
from sources.orderflow import OrderflowSource
from tracker import Tracker
from tracker_context import regime_at


class PerInstrument:
    """Owns one symbol's voices, confluence, judge and tracker."""

    def __init__(
        self,
        cfg: Config,
        inst: InstrumentCfg,
        account: PaperAccount,
        events: EventLog,
        notify: Callable[[str, str], bool],
        memory_provider_factory: Callable[["PerInstrument"], Callable[[], dict[str, Any]]],
    ):
        self.cfg = cfg
        self.inst = inst
        self.symbol = inst.symbol
        self.events = events
        self._notify = notify
        self.voices = list(inst.voices)
        self.confluence_cfg = inst.effective_confluence(cfg.confluence)

        # ---- staleness map (only for the voices this instrument runs) ----
        self._staleness: dict[str, float] = {}

        # ---- Source 1: llm_trader (single-pair bot, one instance per symbol) ----
        # Each symbol may point at its own trader instance via
        # `llm_trader_paths`; otherwise it falls back to the global block (the
        # BTC instance). previous_response.json is derived from the
        # last_analysis_path parent dir inside LlmTraderSource, so overriding
        # these two paths is enough to isolate per-instrument stance reads.
        self.trader: LlmTraderSource | None = None
        if "llm_trader" in self.voices:
            if inst.llm_trader_paths is not None:
                db_path = inst.llm_trader_paths.db_path
                last_analysis_path = inst.llm_trader_paths.last_analysis_path
            else:
                db_path = cfg.llm_trader.db_path
                last_analysis_path = cfg.llm_trader.last_analysis_path
            self.trader = LlmTraderSource(
                db_path,
                last_analysis_path,
                self.symbol,
                cfg.llm_trader.staleness_seconds,
            )
            self._staleness["llm_trader"] = cfg.llm_trader.staleness_seconds

        # ---- Source 2: llm_tradebot (per-symbol) ----
        self.tradebot: LlmTradebotSource | None = None
        if "llm_tradebot" in self.voices:
            self.tradebot = LlmTradebotSource(
                cfg.llm_tradebot.base_url,
                cfg.llm_tradebot.password,
                self.symbol,
                cfg.llm_tradebot.staleness_seconds,
                cfg.llm_tradebot.request_timeout_seconds,
            )
            self._staleness["llm_tradebot"] = cfg.llm_tradebot.staleness_seconds

        # ---- Source 3: orderflow (per-symbol) ----
        of_pw = read_orderflow_password(cfg.orderflow.env_path)
        self.orderflow: OrderflowSource | None = None
        self.tf_builder: TfSummaryBuilder | None = None
        if "orderflow" in self.voices:
            self.orderflow = OrderflowSource(
                cfg.orderflow.host,
                cfg.orderflow.port,
                cfg.orderflow.user,
                cfg.orderflow.db,
                of_pw,
                self.symbol,
                cfg.orderflow.staleness_seconds,
                cfg.orderflow.request_timeout_seconds,
                cfg.orderflow.interval,
                cfg.orderflow.lookback_candles,
                cfg.orderflow.tick_size,
                cfg.orderflow.imbalance_ratio,
                cfg.orderflow.stacked_levels,
                cfg.orderflow.delta_min_abs,
            )
            self._staleness["orderflow"] = cfg.orderflow.staleness_seconds
            # Multi-TF summary builder feeds the judge's TIMEFRAMES section.
            self.tf_builder = TfSummaryBuilder(
                cfg.orderflow.host,
                cfg.orderflow.port,
                cfg.orderflow.user,
                cfg.orderflow.db,
                of_pw,
                self.symbol,
                inst.timeframes,
                cfg.orderflow.tick_size,
                cfg.orderflow.imbalance_ratio,
                cfg.orderflow.request_timeout_seconds,
            )

        # ---- Judge (one call per symbol) ----
        self.judge = Judge(cfg=cfg.judge, symbol=self.symbol)
        self.judge.tf_provider = self._build_tf_summaries
        self.judge.memory_provider = memory_provider_factory(self)
        self._judge_alert_dir = "FLAT"

        # ---- Tracker (per-symbol over shared account) ----
        self.tracker = Tracker(
            cfg=cfg.tracker,
            symbol=self.symbol,
            account=account,
            events=events,
            notify=notify,
            guards_cfg=cfg.guards,
        )

        # ---- Per-voice scorecards (shared db, symbol-scoped) ----
        self.scorecards = Scorecards(
            cfg.scorecards, cfg.tracker.db_path, self.symbol
        )

        # Latest votes (so the memory provider can read the current regime).
        self._last_votes: dict[str, Vote] = {}

    # ---- polling -------------------------------------------------------

    def _source_polls(self) -> list[tuple[str, Callable[[], Vote]]]:
        polls: list[tuple[str, Callable[[], Vote]]] = []
        if self.trader is not None:
            polls.append(("llm_trader", self.trader.poll))
        if self.tradebot is not None:
            polls.append(("llm_tradebot", self.tradebot.poll))
        if self.orderflow is not None:
            polls.append(("orderflow", self.orderflow.poll))
        return polls

    async def poll_votes(self) -> list[Vote]:
        """Run this instrument's source polls in parallel; convert any crash to
        an offline vote so a dead source can't crash the loop."""
        polls = self._source_polls()
        results = await asyncio.gather(
            *(asyncio.to_thread(fn) for _, fn in polls),
            return_exceptions=True,
        )
        votes: list[Vote] = []
        for (name, _), res in zip(polls, results):
            if isinstance(res, Vote):
                votes.append(res.decayed(self._staleness[name]))
            else:
                votes.append(
                    Vote(source=name, direction="offline", detail=f"poll crashed: {res}")
                )
        return votes

    def confluence(self, votes: list[Vote]) -> Confluence:
        return evaluate(
            votes,
            self.confluence_cfg.weights,
            self.confluence_cfg.alert_min_agree,
            self.confluence_cfg.strong_min_agree,
        )

    # ---- judge ---------------------------------------------------------

    def _build_tf_summaries(self) -> list[dict[str, Any]]:
        if self.tf_builder is None:
            return []
        try:
            return summaries_to_dicts(self.tf_builder.build())
        except Exception:
            return []

    def run_judge(self, votes: list[Vote]) -> tuple[JudgeResult, bool]:
        """Run the judge; return (result, fresh?). `fresh` is True when a new
        verdict was produced this tick (a real API call parsed successfully)."""
        vote_map = {v.source: v for v in votes}
        before = self.judge.last_result
        result = self.judge.evaluate(vote_map)
        fresh = result.status == "ok" and result.produced_at != before.produced_at
        return result, fresh

    def maybe_judge_alert(self, result: JudgeResult) -> None:
        """Toast (symbol-prefixed) when the judge flips to LONG/SHORT with
        conviction at/above the configured threshold."""
        if result.direction not in ("LONG", "SHORT"):
            self._judge_alert_dir = result.direction
            return
        threshold = self.cfg.judge.alert_conviction
        changed = result.direction != self._judge_alert_dir
        if changed and result.conviction >= threshold:
            arrow = "▲" if result.direction == "LONG" else "▼"
            title = f"{self.symbol} JUDGE: {result.direction} {arrow}"
            body = (
                f"conviction {result.conviction:.0f} · "
                f"entry {result.entry} · SL {result.stop_loss}"
            )
            fired = self._notify(title, body)
            self.events.append(
                "JUDGE_ALERT",
                {
                    "summary": f"{title} — {body} [toast={'ok' if fired else 'failed'}]",
                    "symbol": self.symbol,
                    "direction": result.direction,
                    "conviction": result.conviction,
                    "toast_fired": fired,
                },
            )
        self._judge_alert_dir = result.direction

    # ---- scorecards ----------------------------------------------------

    def scorecards_tick(self, votes: list[Vote]) -> None:
        """Record voice direction changes + resolve due signals for this symbol.
        Never raises."""
        try:
            directions = {v.source: str(v.direction) for v in votes}
            confidences = {v.source: float(v.confidence) for v in votes}
            vote_map = {v.source: v for v in votes}
            regime = regime_at(vote_map)
            price = self.tracker.last_price
            self.scorecards.on_tick(directions, confidences, price, regime)
        except Exception as exc:  # never crash the loop
            self.scorecards.last_status = f"tick error: {exc}"

    # ---- memory helpers (judge MEMORY section) -------------------------

    def recent_trade_memory(self) -> list[dict[str, Any]]:
        """Compact view of this symbol's last N closed positions."""
        n = self.cfg.judge.memory_last_n
        if n <= 0:
            return []
        out: list[dict[str, Any]] = []
        closed = self.tracker.store.closed_positions_for_symbol(self.symbol)
        for p in closed[:n]:
            ctx = p.context or {}
            line = (
                f"session={ctx.get('session', '?')} "
                f"agree={ctx.get('agree_count', '?')} "
                f"atr%={ctx.get('volatility_atr_percent', '?')}"
            )
            out.append(
                {
                    "direction": p.direction,
                    "conviction": round(p.conviction, 0),
                    "outcome": p.outcome,
                    "r_multiple": round(p.r_multiple, 2) if p.r_multiple is not None else None,
                    "regime": ctx.get("regime", "unknown"),
                    "context_line": line,
                }
            )
        return out

    def scorecard_memory(self, current_regime: str) -> list[dict[str, Any]]:
        snap = self.scorecards.snapshot()
        voices = snap.get("voices", {})
        out: list[dict[str, Any]] = []
        for source, stats in voices.items():
            if stats.get("resolved", 0) == 0:
                continue
            by_regime = stats.get("by_regime", {})
            regime_stats = by_regime.get(current_regime, {})
            out.append(
                {
                    "source": source,
                    "hit_rate": stats.get("hit_rate"),
                    "resolved": stats.get("resolved"),
                    "regime": current_regime,
                    "regime_hit_rate": regime_stats.get("hit_rate"),
                }
            )
        return out

    def current_regime(self) -> str:
        return regime_at(self._last_votes)

    # ---- state ---------------------------------------------------------

    def update_tracker(self, judge_result: JudgeResult, votes: list[Vote]) -> None:
        vote_map = {v.source: v for v in votes}
        self._last_votes = vote_map
        self.tracker.on_tick(judge_result, vote_map)

    def state(self, votes: list[Vote], conf: Confluence, judge_result: JudgeResult) -> dict[str, Any]:
        from main import _conf_to_dict, _vote_to_dict  # local import avoids cycle

        return {
            "symbol": self.symbol,
            "voices": self.voices,
            "votes": [_vote_to_dict(v) for v in votes],
            "confluence": _conf_to_dict(conf),
            "judge": judge_result.to_dict(),
            "tracker": self.tracker.snapshot(),
            "scorecards": self.scorecards.snapshot(),
        }

    def last_judge_ts(self) -> float:
        """Timestamp of this instrument's last real judge call (0.0 if never)."""
        return self.judge.last_call_ts
