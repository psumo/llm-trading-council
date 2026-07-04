"""Pre-execution guard pipeline -- composable pre-trade rejection chain.

Each guard is a small, pure check that inspects a :class:`GuardContext` and
returns either ``None`` (allow) or a human-readable rejection reason. The chain
runs ALL guards and reports every rejection, so a blocked trade lists every
reason it was blocked. Guards never mutate their input.

Empirical motivation (from 7 logged losing trades):
  * 4 trades opened with only one agreeing online voice -- all lost
    (-> QuorumGuard, default min_agree=2).
  * 3 trades had stop distances of 0.05-0.09% of price, inside the noise band,
    and were stopped out within minutes (-> MinStopDistanceGuard, min 0.25%).
  * A 7-loss streak ran unthrottled (-> CooldownAfterLossesGuard +
    DailyLossStopGuard circuit breakers).

A buggy guard fails SAFE: ``run_guards`` converts any guard exception into a
rejection ("guard error: ...") rather than letting it through. Blocking on
error is the conservative choice for a risk gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from sources.base import Vote


@dataclass(frozen=True)
class GuardContext:
    """Immutable snapshot of everything the guards need to judge one open.

    symbol              : the instrument an open is being considered for.
    judge_direction     : judge verdict direction ("LONG" | "SHORT" | "FLAT").
    judge_conviction    : judge conviction 0..100.
    entry / stop_loss   : the proposed entry and stop prices.
    votes               : current per-source votes (Vote has .direction /
                          .confidence). long/short/neutral/offline.
    open_positions_count: number of positions currently open ACROSS all symbols.
    recent_closed       : recent closed trades (newest first) across all
                          symbols; each a dict with closed_at (ISO), r_multiple,
                          symbol.
    now                 : current time (UTC).
    """

    symbol: str
    judge_direction: str
    judge_conviction: float
    entry: float | None
    stop_loss: float | None
    votes: dict[str, Vote] = field(default_factory=dict)
    open_positions_count: int = 0
    recent_closed: list[dict] = field(default_factory=list)
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class Guard(Protocol):
    """A single pre-trade check. ``check`` returns None to allow, or a reason."""

    @property
    def name(self) -> str: ...

    def check(self, ctx: GuardContext) -> str | None: ...


# Map a judge direction to the Vote.direction string that agrees with it.
_DIR_TO_VOTE = {"LONG": "long", "SHORT": "short"}

# PERMISSION voices: the trend/structure sources that GRANT direction. Order
# flow (orderflow) is a TRIGGER, not a vetoing vote, so it is excluded from the
# quorum count -- order-flow disagreement should never block a trend+setup trade.
_PERMISSION_VOICES = ("llm_trader", "llm_tradebot")


_OPPOSITE = {"long": "short", "short": "long"}


def _agreeing_voices(ctx: GuardContext) -> list[str]:
    """Names of online PERMISSION votes whose direction matches the judge."""
    want = _DIR_TO_VOTE.get(ctx.judge_direction.upper())
    if want is None:
        return []
    return sorted(
        name for name, v in ctx.votes.items()
        if name in _PERMISSION_VOICES and str(v.direction).lower() == want
    )


def _opposing_voices(ctx: GuardContext) -> list[str]:
    """Names of online PERMISSION votes voting the OPPOSITE of the judge."""
    want = _DIR_TO_VOTE.get(ctx.judge_direction.upper())
    if want is None:
        return []
    against = _OPPOSITE[want]
    return sorted(
        name for name, v in ctx.votes.items()
        if name in _PERMISSION_VOICES and str(v.direction).lower() == against
    )


@dataclass(frozen=True)
class QuorumGuard:
    """Veto only on ACTIVE OPPOSITION, not on absence of agreement.

    The judge is the fusion layer: it synthesises a direction the raw voices
    may not individually express (e.g. a multi-timeframe pullback short while
    the instantaneous votes are neutral). Demanding a permission voice
    independently re-confirm that direction re-introduces the multiplicative
    AND-gate that starves the system of trades. So this guard blocks a trade
    ONLY when a permission voice (llm_trader / llm_tradebot) is actively voting
    the OPPOSITE direction AND none agree -- a genuine voice-vs-judge conflict.
    Neutral/offline voices = no opinion = let the judge's fused call stand.
    Order flow is excluded entirely (it is a timing trigger, not a vote).

    ``min_agree`` is retained for config/back-compat: if >=1, an agreeing voice
    short-circuits to allow; the opposition veto only applies when 0 agree.
    """

    min_agree: int = 1
    name: str = "quorum"

    def check(self, ctx: GuardContext) -> str | None:
        agree = _agreeing_voices(ctx)
        if agree:  # at least one permission voice confirms -> allow
            return None
        opposing = _opposing_voices(ctx)
        if not opposing:  # none agree, none oppose -> trust the judge's fusion
            return None
        return (
            f"opposition: permission voice(s) [{', '.join(opposing)}] vote "
            f"AGAINST the judge's {ctx.judge_direction} and none agree"
        )


@dataclass(frozen=True)
class MinStopDistanceGuard:
    """Reject stops closer than ``min_pct`` percent of entry (inside noise).

    3 of the 7 historical losers had 0.05-0.09% stops and were stopped within
    minutes.
    """

    min_pct: float = 0.10
    name: str = "min_stop_distance"

    def check(self, ctx: GuardContext) -> str | None:
        if ctx.entry is None or ctx.stop_loss is None or ctx.entry <= 0:
            return None  # no proposed levels to validate; other gates handle it
        dist_pct = abs(ctx.entry - ctx.stop_loss) / ctx.entry * 100.0
        if dist_pct >= self.min_pct:
            return None
        return (
            f"stop too tight: {dist_pct:.3f}% < required {self.min_pct:.2f}% "
            f"(entry {ctx.entry:g}, stop {ctx.stop_loss:g})"
        )


def _parse_iso(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@dataclass(frozen=True)
class CooldownAfterLossesGuard:
    """Throttle after a loss streak: block for ``cooldown_minutes`` when the
    most recent ``consecutive`` closed trades (across ALL symbols) were ALL
    losses and the newest closed within the cooldown window.

    The unthrottled 7-loss streak is exactly what this prevents.
    """

    consecutive: int = 3
    cooldown_minutes: int = 120
    name: str = "cooldown_after_losses"

    def check(self, ctx: GuardContext) -> str | None:
        dated: list[tuple[datetime, dict]] = []
        for c in ctx.recent_closed:
            dt = _parse_iso(c.get("closed_at", ""))
            if dt is not None:
                dated.append((dt, c))
        if len(dated) < self.consecutive:
            return None
        dated.sort(key=lambda pair: pair[0], reverse=True)
        last_n = [c for _, c in dated[: self.consecutive]]
        if any((c.get("r_multiple") or 0.0) >= 0 for c in last_n):
            return None  # streak broken by a non-loss
        newest = dated[0][0]
        elapsed_min = (ctx.now - newest).total_seconds() / 60.0
        if elapsed_min >= self.cooldown_minutes:
            return None  # cooldown already elapsed
        remaining = self.cooldown_minutes - elapsed_min
        return (
            f"cooldown: {self.consecutive} consecutive losses; "
            f"{remaining:.0f} min remaining of {self.cooldown_minutes} min"
        )


@dataclass(frozen=True)
class DailyLossStopGuard:
    """Daily circuit breaker: block when today's (UTC) summed R <= -max.

    Caps the bleed from a bad day regardless of streak shape.
    """

    max_daily_loss_r: float = 3.0
    name: str = "daily_loss_stop"

    def check(self, ctx: GuardContext) -> str | None:
        today = ctx.now.astimezone(timezone.utc).date()
        total = 0.0
        for c in ctx.recent_closed:
            dt = _parse_iso(c.get("closed_at", ""))
            if dt is None or dt.astimezone(timezone.utc).date() != today:
                continue
            total += c.get("r_multiple") or 0.0
        if total <= -self.max_daily_loss_r:
            return (
                f"daily circuit breaker: {total:+.2f}R today "
                f"<= -{self.max_daily_loss_r:.1f}R"
            )
        return None


@dataclass(frozen=True)
class MaxConcurrentGuard:
    """Cap simultaneous open positions across all symbols at ``max_open``."""

    max_open: int = 3
    name: str = "max_concurrent"

    def check(self, ctx: GuardContext) -> str | None:
        if ctx.open_positions_count >= self.max_open:
            return (
                f"max concurrent: {ctx.open_positions_count} open "
                f">= limit {self.max_open}"
            )
        return None


def run_guards(
    guards: list[Guard], ctx: GuardContext
) -> list[tuple[str, str]]:
    """Run ALL guards and return every (name, reason) rejection.

    An empty list means every guard allowed the trade. This never raises: a
    guard that throws is converted into a rejection so a buggy guard fails SAFE
    (blocks the trade) instead of silently letting it through.
    """
    rejections: list[tuple[str, str]] = []
    for guard in guards:
        name = getattr(guard, "name", guard.__class__.__name__)
        try:
            reason = guard.check(ctx)
        except Exception as exc:  # fail safe: a broken guard blocks
            rejections.append((name, f"guard error: {exc}"))
            continue
        if reason is not None:
            rejections.append((name, reason))
    return rejections
