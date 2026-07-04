"""Immutable data models for the paper-trading position tracker.

A Position is a single virtual trade derived from a judge verdict. It is opened
when the judge is decisive enough and carries the levels (entry/SL/TP) plus the
risk math needed to score the outcome. All updates return new copies -- the
dataclasses are frozen so a position is never mutated in place.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any

# Round-trip trading cost charged per side, in basis points (1 bp = 0.01%).
# Default 4.0 bps/side is a typical taker fee+slippage assumption. Overridable
# via the AGG_FEE_BPS_PER_SIDE env var for tests / tuning.
# NOTE (coordinator): move this into config.yaml / TrackerCfg later -- the config
# files are concurrently owned by another agent and must not be edited here.
FEE_BPS_PER_SIDE = 4.0


def _fee_bps_per_side() -> float:
    """Resolve the per-side fee in bps (env override, else module default)."""
    raw = os.environ.get("AGG_FEE_BPS_PER_SIDE")
    if raw is None:
        return FEE_BPS_PER_SIDE
    try:
        return max(0.0, float(raw))
    except ValueError:
        return FEE_BPS_PER_SIDE


@dataclass(frozen=True)
class Position:
    """One virtual (paper) position. `id` is a monotonically increasing int."""

    id: int
    opened_at: str  # ISO8601 UTC
    direction: str  # "LONG" | "SHORT"
    conviction: float
    entry: float
    stop_loss: float
    symbol: str  # e.g. "BTCUSDT" -- one open position per symbol
    take_profit_1: float | None
    take_profit_2: float | None
    risk_reward: float | None
    rationale: str
    # The three source directions captured at open (e.g. {"orderflow":"long"}).
    source_dirs: dict[str, str] = field(default_factory=dict)
    # Entry-condition snapshot (regime/session/levels/agreement...). See
    # tracker_context.build_context. Empty dict when not captured.
    context: dict[str, Any] = field(default_factory=dict)
    # Position sizing in USD risk and notional units, derived at open.
    risk_usd: float = 0.0
    size_units: float = 0.0
    # Judge entry vs live price reconciliation at open.
    judge_entry: float | None = None
    live_entry: float | None = None
    # Excursion tracking (filled in live).
    max_favorable: float = 0.0  # best unrealized R seen
    max_adverse: float = 0.0  # worst unrealized R seen (<= 0)
    last_price: float | None = None
    # Close fields (None while open).
    closed_at: str | None = None
    exit_price: float | None = None
    outcome: str | None = None  # "win" | "loss" | "flip" | "timeout"
    r_multiple: float | None = None  # AFTER round-trip fees (used for stats)
    pnl_pct: float | None = None
    pnl_usd: float | None = None
    # Gross R before fees (kept for transparency / fee-impact analysis).
    r_gross: float | None = None
    # Cumulative time the market was actually live for this position (seconds).
    # Incremented only on non-stale ticks so a frozen off-hours instrument does
    # not accrue hold time and mass-timeout at the session reopen gap.
    active_seconds: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def risk_distance(self) -> float:
        """Absolute price distance from entry to stop (always > 0 for a valid
        position)."""
        return abs(self.entry - self.stop_loss)

    def with_excursion(self, price: float) -> "Position":
        """Return a copy updated with the latest price and MFE/MAE in R."""
        r = unrealized_r(self, price)
        return replace(
            self,
            last_price=price,
            max_favorable=max(self.max_favorable, r),
            max_adverse=min(self.max_adverse, r),
        )

    def with_active_time(self, delta_seconds: float) -> "Position":
        """Return a copy with `delta_seconds` of live market time added.

        Called once per non-stale tick. Negative/NaN deltas are clamped to 0 so
        a clock glitch cannot rewind accrued hold time.
        """
        if delta_seconds != delta_seconds or delta_seconds < 0:  # NaN or <0
            delta_seconds = 0.0
        return replace(self, active_seconds=self.active_seconds + delta_seconds)

    @property
    def active_hours(self) -> float:
        """Live-market hold time in hours (drives the timeout rule)."""
        return self.active_seconds / 3600.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "opened_at": self.opened_at,
            "direction": self.direction,
            "conviction": self.conviction,
            "symbol": self.symbol,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "risk_reward": self.risk_reward,
            "rationale": self.rationale,
            "source_dirs": self.source_dirs,
            "context": self.context,
            "risk_usd": self.risk_usd,
            "size_units": self.size_units,
            "judge_entry": self.judge_entry,
            "live_entry": self.live_entry,
            "max_favorable": self.max_favorable,
            "max_adverse": self.max_adverse,
            "last_price": self.last_price,
            "closed_at": self.closed_at,
            "exit_price": self.exit_price,
            "outcome": self.outcome,
            "r_multiple": self.r_multiple,
            "pnl_pct": self.pnl_pct,
            "pnl_usd": self.pnl_usd,
            "r_gross": self.r_gross,
            "active_seconds": self.active_seconds,
        }


def unrealized_r(pos: Position, price: float) -> float:
    """Signed R multiple at `price` given the position's entry and stop.

    LONG profits as price rises; SHORT profits as price falls. R is the signed
    price move divided by the entry-to-stop risk distance.
    """
    risk = pos.risk_distance
    if risk <= 0:
        return 0.0
    if pos.direction == "LONG":
        return (price - pos.entry) / risk
    return (pos.entry - price) / risk


def realized_close(
    pos: Position,
    exit_price: float,
    outcome: str,
    closed_at: str,
) -> Position:
    """Return a closed copy of `pos` with R, pnl_pct and pnl_usd computed.

    R is the realized signed move / risk distance, charged round-trip fees.
    pnl_pct is the signed price return relative to entry (in the trade's
    favour). pnl_usd = net-R * risk_usd.

    Fee model: a fee is charged on BOTH the entry and exit fills. The notional
    of each leg is size_units * price, so the round-trip fee in USD is::

        fee_usd = size_units * (entry + exit) * fee_bps_per_side / 10000

    (fee_bps_per_side/10000 applied once to entry notional and once to exit
    notional). Converting to R divides by risk_usd. Both the after-fee R
    (`r_multiple`, used for stats) and the gross R (`r_gross`) are stored.
    """
    r_gross = unrealized_r(pos, exit_price)
    if pos.entry > 0:
        raw_pct = (exit_price - pos.entry) / pos.entry * 100.0
        pnl_pct = raw_pct if pos.direction == "LONG" else -raw_pct
    else:
        pnl_pct = 0.0

    fee_bps = _fee_bps_per_side()
    fee_usd = pos.size_units * (pos.entry + exit_price) * fee_bps / 10000.0
    if pos.risk_usd > 0:
        r_net = r_gross - fee_usd / pos.risk_usd
    else:
        r_net = r_gross
    pnl_usd = r_net * pos.risk_usd
    return replace(
        pos,
        closed_at=closed_at,
        exit_price=exit_price,
        outcome=outcome,
        r_multiple=r_net,
        r_gross=r_gross,
        pnl_pct=pnl_pct,
        pnl_usd=pnl_usd,
        last_price=exit_price,
    )


def decide_close(
    pos: Position,
    price: float,
    judge_direction: str,
    judge_conviction: float,
    min_conviction: float,
    age_hours: float,
    max_hold_hours: float,
) -> tuple[str, float] | None:
    """Pure close-rule evaluation.

    Returns (outcome, exit_price) when the position should close, else None.
    Precedence: stop-loss, then take-profit-1, then judge flip, then timeout.
    Stop/TP exit at their exact level (a touch closes the trade); flip and
    timeout exit at the current market price.

    `age_hours` is the position's LIVE-market hold time (see
    Position.active_hours), not wall-clock age, so a frozen off-hours
    instrument does not time out at the session reopen.
    """
    opp = "SHORT" if pos.direction == "LONG" else "LONG"

    if pos.direction == "LONG":
        if price <= pos.stop_loss:
            return ("loss", pos.stop_loss)
        if pos.take_profit_1 is not None and price >= pos.take_profit_1:
            return ("win", pos.take_profit_1)
    else:  # SHORT
        if price >= pos.stop_loss:
            return ("loss", pos.stop_loss)
        if pos.take_profit_1 is not None and price <= pos.take_profit_1:
            return ("win", pos.take_profit_1)

    if judge_direction == opp and judge_conviction >= min_conviction:
        return ("flip", price)

    if age_hours >= max_hold_hours:
        return ("timeout", price)

    return None
