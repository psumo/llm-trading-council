"""Tests for the entry-context builder (tracker_context.build_context).

Given fixture vote extras + a judge verdict, assert the derived tags: regime,
session, day_of_week, agreement, and price-vs-levels distances.
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from judge import JudgeResult  # noqa: E402
from sources.base import Vote  # noqa: E402
from tracker_context import (  # noqa: E402
    build_context,
    classify_regime,
    classify_session,
)


def _trader_vote(adx, chop, atr_pct, support, resistance, direction="long") -> Vote:
    return Vote(
        source="llm_trader",
        direction=direction,
        confidence=0.8,
        age_seconds=10.0,
        detail="x",
        extra={
            "indicators": {
                "adx": adx,
                "choppiness": chop,
                "atr_percent": atr_pct,
                "basic_support": support,
                "basic_resistance": resistance,
            }
        },
    )


def _judge(direction="LONG", model="gemini-3.5-flash") -> JudgeResult:
    return JudgeResult(
        status="ok",
        direction=direction,
        conviction=70.0,
        entry=100.0,
        stop_loss=95.0,
        risk_reward=2.0,
        model=model,
    )


# ---- regime classification --------------------------------------------


def test_classify_regime_buckets() -> None:
    assert classify_regime(None) == "unknown"
    assert classify_regime(10.0) == "chop"
    assert classify_regime(19.99) == "chop"
    assert classify_regime(20.0) == "weak_trend"
    assert classify_regime(25.0) == "weak_trend"
    assert classify_regime(25.01) == "trend"
    assert classify_regime(40.0) == "trend"


def test_classify_session_hours() -> None:
    assert classify_session(0) == "asia"
    assert classify_session(6) == "asia"
    assert classify_session(7) == "eu"
    assert classify_session(12) == "eu"
    assert classify_session(13) == "us"
    assert classify_session(21) == "us"
    assert classify_session(22) == "late"
    assert classify_session(23) == "late"


# ---- full context build -----------------------------------------------


def test_build_context_trend_us_session() -> None:
    votes = {
        "llm_trader": _trader_vote(30.0, 40.0, 1.2, 95.0, 110.0, "long"),
        "llm_tradebot": Vote(source="llm_tradebot", direction="long", confidence=0.7),
        "orderflow": Vote(source="orderflow", direction="short", confidence=0.6),
    }
    # 2026-06-12 is a Friday; 15:00 UTC -> us session.
    ctx = build_context(votes, _judge("LONG"), "2026-06-12T15:00:00+00:00", 100.0)

    assert ctx["regime"] == "trend"
    assert ctx["adx"] == 30.0
    assert ctx["choppiness"] == 40.0
    assert ctx["volatility_atr_percent"] == 1.2
    assert ctx["session"] == "us"
    assert ctx["hour_utc"] == 15
    assert ctx["day_of_week"] == "friday"
    assert ctx["judge_direction"] == "LONG"
    assert ctx["conviction"] == 70.0
    assert ctx["risk_reward"] == 2.0
    assert ctx["judge_model"] == "gemini-3.5-flash"
    # trader + tradebot are long (agree with LONG); orderflow short does not.
    assert ctx["agree_count"] == 2
    assert ctx["agreed_sources"] == ["llm_tradebot", "llm_trader"]  # sorted
    assert ctx["source_directions"]["orderflow"] == "short"
    # entry 100: support 95 -> 5% below; resistance 110 -> 10% above.
    assert ctx["price_vs_levels"]["dist_to_support_pct"] == 5.0
    assert ctx["price_vs_levels"]["dist_to_resistance_pct"] == 10.0


def test_build_context_missing_indicators_unknown_regime() -> None:
    votes = {
        "llm_trader": Vote(source="llm_trader", direction="neutral", extra={}),
        "llm_tradebot": Vote(source="llm_tradebot", direction="offline"),
        "orderflow": Vote(source="orderflow", direction="short", confidence=0.6),
    }
    ctx = build_context(votes, _judge("SHORT"), "2026-06-12T03:00:00+00:00", 100.0)
    assert ctx["regime"] == "unknown"
    assert ctx["adx"] is None
    assert ctx["session"] == "asia"
    # only orderflow (short) agrees with the SHORT judge.
    assert ctx["agree_count"] == 1
    assert ctx["agreed_sources"] == ["orderflow"]
    # no indicators -> no level distances.
    assert ctx["price_vs_levels"] == {}
