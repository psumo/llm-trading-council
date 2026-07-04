"""Performance statistics computed on the fly from closed positions.

Pure functions over a list of closed Position objects plus the equity curve.
No I/O here -- the caller pulls rows from the store and passes them in.

Win/loss accounting:
  Classified by the sign of NET realized R (after fees), NOT by the close-reason
  label. The `outcome` field ("win"/"loss"/"flip"/"timeout") only records WHY a
  position closed (which level was hit) -- a take-profit hit whose tiny reward is
  eaten by fees nets negative R and must count as a LOSS, otherwise win-rate
  contradicts the equity curve (the "100% win rate, negative return" paradox).
  R > 0 -> win, R < 0 -> loss, R == 0 -> scratch (ignored for win rate).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from tracker_models import Position


def _is_win(pos: Position) -> bool | None:
    """True=win, False=loss, None=scratch (R==0). By NET R sign, not the
    close-reason label -- so the win-rate always agrees with realized PnL."""
    r = pos.r_multiple
    if r is None or r == 0:
        return None
    return r > 0


def _hold_seconds(pos: Position) -> float | None:
    if not pos.opened_at or not pos.closed_at:
        return None
    try:
        opened = datetime.fromisoformat(pos.opened_at)
        closed = datetime.fromisoformat(pos.closed_at)
    except ValueError:
        return None
    return max(0.0, (closed - opened).total_seconds())


def _max_drawdown(curve: list[tuple[str, float]]) -> float:
    """Largest peak-to-trough drop on the equity curve, as a percentage."""
    peak = float("-inf")
    max_dd = 0.0
    for _, bal in curve:
        peak = max(peak, bal)
        if peak > 0:
            dd = (peak - bal) / peak * 100.0
            max_dd = max(max_dd, dd)
    return max_dd


def _direction_breakdown(closed: list[Position]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for side in ("LONG", "SHORT"):
        side_trades = [p for p in closed if p.direction == side]
        wins = sum(1 for p in side_trades if _is_win(p) is True)
        losses = sum(1 for p in side_trades if _is_win(p) is False)
        rs = [p.r_multiple for p in side_trades if p.r_multiple is not None]
        decided = wins + losses
        out[side.lower()] = {
            "trades": len(side_trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / decided * 100.0, 1) if decided else 0.0,
            "cumulative_r": round(sum(rs), 3),
        }
    return out


def compute_stats(
    closed: list[Position],
    equity_curve: list[tuple[str, float]],
    balance: float,
    start_balance: float,
) -> dict[str, Any]:
    """Full performance summary. `closed` may be in any order."""
    total = len(closed)
    rs = [p.r_multiple for p in closed if p.r_multiple is not None]
    wins = sum(1 for p in closed if _is_win(p) is True)
    losses = sum(1 for p in closed if _is_win(p) is False)
    decided = wins + losses

    gross_win = sum(r for r in rs if r > 0)
    gross_loss = sum(-r for r in rs if r < 0)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (
        float(gross_win) if gross_win > 0 else 0.0
    )

    best = max(rs) if rs else 0.0
    worst = min(rs) if rs else 0.0
    holds = [h for h in (_hold_seconds(p) for p in closed) if h is not None]
    avg_hold_seconds = (sum(holds) / len(holds)) if holds else 0.0

    total_return_pct = (
        (balance - start_balance) / start_balance * 100.0 if start_balance > 0 else 0.0
    )

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / decided * 100.0, 1) if decided else 0.0,
        "avg_r": round(sum(rs) / len(rs), 3) if rs else 0.0,
        "cumulative_r": round(sum(rs), 3),
        "profit_factor": round(profit_factor, 2),
        "best_trade_r": round(best, 3),
        "worst_trade_r": round(worst, 3),
        "balance": round(balance, 2),
        "start_balance": round(start_balance, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(_max_drawdown(equity_curve), 2),
        "avg_hold_seconds": round(avg_hold_seconds, 0),
        "by_direction": _direction_breakdown(closed),
    }
