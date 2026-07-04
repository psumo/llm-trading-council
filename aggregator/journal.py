"""Trade journal: closed positions + conditional performance aggregates.

Pure functions over a list of closed Position objects. Each closed position
carries its entry `context` (see tracker_context.build_context), so we can
group win rate and average R by the conditions a trade was opened into:
regime, session, agree_count and direction.

No I/O -- main.py pulls closed positions from the store and passes them in.
"""
from __future__ import annotations

from typing import Any

from tracker_models import Position


def _is_win(pos: Position) -> bool | None:
    if pos.outcome == "win":
        return True
    if pos.outcome == "loss":
        return False
    r = pos.r_multiple
    if r is None or r == 0:
        return None
    return r > 0


def _group_key(pos: Position, dimension: str) -> str:
    ctx = pos.context or {}
    if dimension == "direction":
        return str(pos.direction or "unknown")
    if dimension == "symbol":
        return str(pos.symbol or "unknown")
    if dimension == "agree_count":
        val = ctx.get("agree_count")
        return str(val) if val is not None else "unknown"
    value = ctx.get(dimension)
    return str(value) if value not in (None, "") else "unknown"


def _bucket_stats(group: list[Position]) -> dict[str, Any]:
    wins = sum(1 for p in group if _is_win(p) is True)
    losses = sum(1 for p in group if _is_win(p) is False)
    decided = wins + losses
    rs = [p.r_multiple for p in group if p.r_multiple is not None]
    return {
        "trades": len(group),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / decided * 100.0, 1) if decided else None,
        "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
        "cumulative_r": round(sum(rs), 3) if rs else 0.0,
    }


def _group_by(closed: list[Position], dimension: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[Position]] = {}
    for pos in closed:
        key = _group_key(pos, dimension)
        buckets.setdefault(key, []).append(pos)
    return {key: _bucket_stats(group) for key, group in sorted(buckets.items())}


def _entry_row(pos: Position) -> dict[str, Any]:
    ctx = pos.context or {}
    return {
        "id": pos.id,
        "opened_at": pos.opened_at,
        "closed_at": pos.closed_at,
        "symbol": pos.symbol,
        "direction": pos.direction,
        "conviction": pos.conviction,
        "outcome": pos.outcome,
        "r_multiple": pos.r_multiple,
        "pnl_usd": pos.pnl_usd,
        "regime": ctx.get("regime", "unknown"),
        "session": ctx.get("session", "unknown"),
        "agree_count": ctx.get("agree_count"),
        "context": ctx,
    }


def build_journal(
    closed: list[Position], symbol: str | None = None
) -> dict[str, Any]:
    """All closed positions with context + outcome, plus conditional aggregates.

    `closed` may be in any order. When `symbol` is given, only that symbol's
    trades are included (and the per-symbol breakdown collapses to one bucket).
    When empty, aggregates are empty dicts and the dashboard hides the section.
    """
    if symbol is not None:
        sym = symbol.strip().upper()
        closed = [p for p in closed if (p.symbol or "").upper() == sym]
    trades = [_entry_row(p) for p in closed]
    aggregates: dict[str, Any] = {}
    if closed:
        aggregates = {
            "by_symbol": _group_by(closed, "symbol"),
            "by_regime": _group_by(closed, "regime"),
            "by_session": _group_by(closed, "session"),
            "by_agree_count": _group_by(closed, "agree_count"),
            "by_direction": _group_by(closed, "direction"),
        }
    return {
        "count": len(closed),
        "symbol": symbol,
        "trades": trades,
        "aggregates": aggregates,
    }
