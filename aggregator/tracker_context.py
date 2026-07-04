"""Entry-context snapshot builder for the paper-trading tracker.

Pure functions: given the source votes at open, the judge verdict and the open
timestamp, derive a compact JSON-able context dict describing the market
conditions a position was opened into. This is stored on the position row so
that closed trades carry the full conditions for the journal and reflection.

No I/O, no mutation -- every helper returns a new value.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from judge import JudgeResult
from sources.base import Vote

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _trader_indicators(votes: dict[str, Vote]) -> dict[str, Any]:
    """The llm_trader curated-indicator subset, or empty when unavailable."""
    trader = votes.get("llm_trader")
    if trader is None:
        return {}
    ind = trader.extra.get("indicators")
    return ind if isinstance(ind, dict) else {}


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_regime(adx: float | None) -> str:
    """ADX -> regime bucket. Missing ADX is 'unknown'."""
    if adx is None:
        return "unknown"
    if adx < 20:
        return "chop"
    if adx <= 25:
        return "weak_trend"
    return "trend"


def classify_session(hour_utc: int) -> str:
    """UTC hour -> trading session label."""
    if 0 <= hour_utc < 7:
        return "asia"
    if 7 <= hour_utc < 13:
        return "eu"
    if 13 <= hour_utc < 22:
        return "us"
    return "late"


def _price_vs_levels(
    indicators: dict[str, Any], entry: float | None
) -> dict[str, float | None]:
    """Percent distance from entry to llm_trader's basic S/R, if present."""
    out: dict[str, float | None] = {}
    if entry is None or entry <= 0:
        return out
    support = _num(indicators.get("basic_support"))
    resistance = _num(indicators.get("basic_resistance"))
    if support is not None:
        out["dist_to_support_pct"] = round((entry - support) / entry * 100.0, 4)
    if resistance is not None:
        out["dist_to_resistance_pct"] = round((resistance - entry) / entry * 100.0, 4)
    return out


def _direction_matches(source_dir: str, judge_dir: str) -> bool:
    """A source agrees with the judge when long<->LONG / short<->SHORT."""
    s = (source_dir or "").lower()
    j = (judge_dir or "").upper()
    if j == "LONG":
        return s == "long"
    if j == "SHORT":
        return s == "short"
    return False


def build_context(
    votes: dict[str, Vote],
    judge: JudgeResult,
    opened_at: str,
    entry: float,
) -> dict[str, Any]:
    """Snapshot the entry conditions for a freshly opened position.

    `opened_at` is an ISO8601 UTC string; `entry` the fill price used.
    """
    indicators = _trader_indicators(votes)
    adx = _num(indicators.get("adx"))
    choppiness = _num(indicators.get("choppiness"))
    atr_percent = _num(indicators.get("atr_percent"))

    try:
        opened_dt = datetime.fromisoformat(opened_at)
    except ValueError:
        opened_dt = datetime.now(timezone.utc)
    if opened_dt.tzinfo is None:
        opened_dt = opened_dt.replace(tzinfo=timezone.utc)
    opened_dt = opened_dt.astimezone(timezone.utc)

    source_directions = {k: str(v.direction) for k, v in votes.items()}
    agreed_sources = [
        k
        for k, v in votes.items()
        if _direction_matches(str(v.direction), judge.direction)
    ]

    return {
        "regime": classify_regime(adx),
        "adx": adx,
        "choppiness": choppiness,
        "volatility_atr_percent": atr_percent,
        "session": classify_session(opened_dt.hour),
        "hour_utc": opened_dt.hour,
        "day_of_week": _DAYS[opened_dt.weekday()],
        "source_directions": source_directions,
        "agree_count": len(agreed_sources),
        "agreed_sources": sorted(agreed_sources),
        "judge_direction": judge.direction,
        "conviction": judge.conviction,
        "risk_reward": judge.risk_reward,
        "judge_model": judge.model,
        "price_vs_levels": _price_vs_levels(indicators, entry),
    }


def regime_at(votes: dict[str, Vote]) -> str:
    """Convenience: just the regime label from the current votes (for the
    scorecards, which tag each recorded signal with the regime at signal time)."""
    indicators = _trader_indicators(votes)
    return classify_regime(_num(indicators.get("adx")))
