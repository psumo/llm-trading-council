"""Multi-timeframe order-flow summary builder + the judge TIMEFRAMES section.

Covers the pure row->summary mapping (delta/volume/close/stacked counts) and the
prompt section that combines per-TF order-flow with the tradebot's per-TF trend
scores, including the empty-on-cold-start case and the tf_alignment plumbing.
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from judge import (  # noqa: E402
    JudgeResult,
    build_prompt,
    build_timeframes_section,
    parse_response,
)
from orderflow_tf import TfSummary, _summarize_row  # noqa: E402
from sources.base import Vote  # noqa: E402


def _levels_buy_stacked() -> dict:
    # Buy-imbalanced levels (bid >> ask one tick below). The lowest level has no
    # neighbour below it so it cannot be imbalanced -> 4 levels give a stack of 3.
    return {
        "99.9": {"volSumBid": 90, "volSumAsk": 1},
        "100.0": {"volSumBid": 90, "volSumAsk": 1},
        "100.1": {"volSumBid": 90, "volSumAsk": 1},
        "100.2": {"volSumBid": 90, "volSumAsk": 1},
    }


# ---- pure row -> summary ----------------------------------------------


def test_summarize_row_builds_stacked_summary() -> None:
    open_time = datetime.now(timezone.utc)
    row = (open_time, 123.5, _levels_buy_stacked(), 100.2, 4500.0)
    s = _summarize_row("5m", row, tick=0.1, ratio=3.0)
    assert s.timeframe == "5m"
    assert s.status == "ok"
    assert s.delta == 123.5
    assert s.total_volume == 4500.0
    assert s.close == 100.2
    assert s.buy_stack >= 3   # three consecutive buy-imbalanced levels
    assert s.sell_stack == 0
    assert s.age_seconds is not None and s.age_seconds >= 0


def test_summarize_row_handles_bad_numbers() -> None:
    row = (None, "not-a-number", {}, None, None)
    s = _summarize_row("1h", row, tick=0.1, ratio=3.0)
    assert s.status == "ok"
    assert s.delta is None
    assert s.total_volume is None
    assert s.close is None
    assert s.buy_stack == 0 and s.sell_stack == 0
    assert s.age_seconds is None  # openTime was None


# ---- judge TIMEFRAMES section -----------------------------------------


def _tradebot_vote_with_trends() -> Vote:
    return Vote(
        source="llm_tradebot",
        direction="long",
        confidence=0.7,
        extra={"vote_details": {"trend_1h": 60, "trend_15m": -20, "trend_5m": -60}},
    )


def test_tf_section_empty_on_cold_start() -> None:
    # No usable summaries and no tradebot trends -> empty (prompt unchanged).
    assert build_timeframes_section(None, {}) == ""
    assert build_timeframes_section([], {"orderflow": Vote(source="orderflow")}) == ""
    no_ok = [TfSummary("5m", "no_data").to_dict()]
    assert build_timeframes_section(no_ok, {}) == ""


def test_tf_section_renders_orderflow_and_trends() -> None:
    summaries = [
        TfSummary("5m", "ok", delta=120.0, total_volume=4000.0, close=100.2,
                  buy_stack=3, sell_stack=0).to_dict(),
        TfSummary("15m", "ok", delta=-50.0, total_volume=9000.0, close=100.1,
                  buy_stack=0, sell_stack=2).to_dict(),
    ]
    votes = {"llm_tradebot": _tradebot_vote_with_trends()}
    block = build_timeframes_section(summaries, votes)
    assert "TIMEFRAMES" in block
    assert "5m: delta=+120.00" in block
    assert "15m: delta=-50.00" in block
    assert "buy_stack=3" in block
    # tradebot trend scores rendered per timeframe.
    assert "1h: 60" in block
    assert "15m: -20" in block
    assert "5m: -60" in block


def test_build_prompt_includes_timeframes_when_supplied() -> None:
    summaries = [
        TfSummary("1h", "ok", delta=10.0, total_volume=1.0, close=100.0).to_dict()
    ]
    votes = {"orderflow": Vote(source="orderflow", direction="long")}
    with_tf = build_prompt(votes, "BTCUSDT", 100.0, None, summaries)
    without_tf = build_prompt(votes, "BTCUSDT", 100.0, None, None)
    assert "TIMEFRAMES" in with_tf
    assert "TIMEFRAMES" not in without_tf


def test_parse_response_carries_tf_alignment() -> None:
    raw = (
        '{"direction":"LONG","conviction":70,"position_size_pct":50,'
        '"timeframe":"15m","tf_alignment":"1h up, 15m flat, 5m up -- aligned long",'
        '"rationale":"r","invalidation":"i","disagreements":"d"}'
    )
    res = parse_response(raw, "test-model", 1, 0.0)
    assert isinstance(res, JudgeResult)
    assert res.tf_alignment == "1h up, 15m flat, 5m up -- aligned long"
    # round-trips through to_dict for /api/state.
    assert res.to_dict()["tf_alignment"] == res.tf_alignment
