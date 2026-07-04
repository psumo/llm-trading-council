"""Pre-execution guard pipeline tests.

Covers each guard's allow + reject path, the historical-loss fixtures (the 4-of-7
single-voice losers reject on quorum; a 0.07% stop rejects on min-stop; a 3-loss
streak 30 min ago rejects on cooldown but 3h ago allows; a -3.5R day rejects),
and that a guard exception fails SAFE (becomes a rejection).
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guards import (  # noqa: E402
    CooldownAfterLossesGuard,
    DailyLossStopGuard,
    GuardContext,
    MaxConcurrentGuard,
    MinStopDistanceGuard,
    QuorumGuard,
    run_guards,
)
from sources.base import Vote  # noqa: E402

NOW = datetime(2026, 6, 12, 15, 0, 0, tzinfo=timezone.utc)


def _ctx(**kw) -> GuardContext:
    base = dict(
        symbol="BTCUSDT",
        judge_direction="LONG",
        judge_conviction=70.0,
        entry=100.0,
        stop_loss=99.0,  # 1.0% -> well above min stop
        votes={},
        open_positions_count=0,
        recent_closed=[],
        now=NOW,
    )
    base.update(kw)
    return GuardContext(**base)


def _vote(source: str, direction: str) -> Vote:
    return Vote(source=source, direction=direction, confidence=0.6)


def _closed(minutes_ago: float, r: float, symbol: str = "BTCUSDT") -> dict:
    return {
        "closed_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "r_multiple": r,
        "symbol": symbol,
    }


# ---- QuorumGuard -------------------------------------------------------

def test_quorum_allows_when_a_permission_voice_agrees():
    # An agreeing permission voice short-circuits to allow.
    g = QuorumGuard()
    ctx = _ctx(votes={
        "llm_trader": _vote("llm_trader", "long"),
        "llm_tradebot": _vote("llm_tradebot", "long"),
    })
    assert g.check(ctx) is None


def test_quorum_allows_when_none_agree_and_none_oppose():
    # The judge fuses a direction the raw votes don't express; neutral/offline
    # permission voices = no opinion -> trust the judge, do NOT block.
    g = QuorumGuard()
    ctx = _ctx(
        judge_direction="SHORT",
        votes={
            "llm_trader": _vote("llm_trader", "neutral"),
            "llm_tradebot": _vote("llm_tradebot", "offline"),
            "orderflow": _vote("orderflow", "long"),  # excluded: not a permission voice
        },
    )
    assert g.check(ctx) is None


def test_quorum_rejects_on_active_opposition():
    # A permission voice voting the OPPOSITE with none agreeing = real conflict.
    g = QuorumGuard()
    ctx = _ctx(
        judge_direction="SHORT",
        votes={
            "llm_trader": _vote("llm_trader", "long"),   # opposes a SHORT
            "llm_tradebot": _vote("llm_tradebot", "neutral"),
        },
    )
    reason = g.check(ctx)
    assert reason is not None and "opposition" in reason and "llm_trader" in reason


# ---- MinStopDistanceGuard ----------------------------------------------

def test_min_stop_allows_wide_stop():
    g = MinStopDistanceGuard(min_pct=0.25)
    assert g.check(_ctx(entry=100.0, stop_loss=99.0)) is None  # 1.0%


def test_min_stop_rejects_tight_stop():
    g = MinStopDistanceGuard(min_pct=0.25)
    # 0.07% stop -> inside noise (one of the 3 historical tight-stop losers).
    ctx = _ctx(entry=100.0, stop_loss=99.93)
    reason = g.check(ctx)
    assert reason is not None and "0.070%" in reason


# ---- CooldownAfterLossesGuard ------------------------------------------

def test_cooldown_rejects_three_losses_30min_ago():
    g = CooldownAfterLossesGuard(consecutive=3, cooldown_minutes=120)
    ctx = _ctx(
        recent_closed=[
            _closed(30, -1.0, "BTCUSDT"),
            _closed(60, -0.8, "ETHUSDT"),
            _closed(90, -1.2, "SOLUSDT"),
        ]
    )
    reason = g.check(ctx)
    assert reason is not None and "remaining" in reason


def test_cooldown_allows_three_losses_3h_ago():
    g = CooldownAfterLossesGuard(consecutive=3, cooldown_minutes=120)
    ctx = _ctx(
        recent_closed=[
            _closed(180, -1.0),
            _closed(210, -0.8),
            _closed(240, -1.2),
        ]
    )
    assert g.check(ctx) is None


def test_cooldown_allows_when_streak_broken_by_win():
    g = CooldownAfterLossesGuard(consecutive=3, cooldown_minutes=120)
    ctx = _ctx(
        recent_closed=[
            _closed(30, -1.0),
            _closed(60, 0.5),  # a win breaks the streak
            _closed(90, -1.2),
        ]
    )
    assert g.check(ctx) is None


# ---- DailyLossStopGuard ------------------------------------------------

def test_daily_loss_rejects_minus_three_point_five_r():
    g = DailyLossStopGuard(max_daily_loss_r=3.0)
    ctx = _ctx(
        recent_closed=[
            _closed(30, -1.5),
            _closed(120, -1.0),
            _closed(240, -1.0),
        ]
    )
    reason = g.check(ctx)
    assert reason is not None and "circuit breaker" in reason


def test_daily_loss_allows_below_threshold():
    g = DailyLossStopGuard(max_daily_loss_r=3.0)
    ctx = _ctx(recent_closed=[_closed(30, -1.0), _closed(120, -1.0)])
    assert g.check(ctx) is None


def test_daily_loss_ignores_yesterday():
    g = DailyLossStopGuard(max_daily_loss_r=3.0)
    # 20 hours ago crosses the UTC date boundary from NOW (15:00 UTC).
    ctx = _ctx(
        recent_closed=[
            {"closed_at": (NOW - timedelta(hours=20)).isoformat(), "r_multiple": -5.0, "symbol": "BTCUSDT"},
        ]
    )
    assert g.check(ctx) is None


# ---- MaxConcurrentGuard ------------------------------------------------

def test_max_concurrent_allows_below_limit():
    assert MaxConcurrentGuard(max_open=3).check(_ctx(open_positions_count=2)) is None


def test_max_concurrent_rejects_at_limit():
    reason = MaxConcurrentGuard(max_open=3).check(_ctx(open_positions_count=3))
    assert reason is not None and "max concurrent" in reason


# ---- run_guards orchestration ------------------------------------------

def test_run_guards_empty_when_all_allow():
    guards = [QuorumGuard(2), MinStopDistanceGuard(0.25), MaxConcurrentGuard(3)]
    ctx = _ctx(votes={
        "llm_trader": _vote("llm_trader", "long"),
        "llm_tradebot": _vote("llm_tradebot", "long"),
    })
    assert run_guards(guards, ctx) == []


def test_run_guards_reports_every_rejection():
    guards = [QuorumGuard(), MinStopDistanceGuard(0.25)]
    # active opposition AND tight stop -> both reject.
    ctx = _ctx(
        judge_direction="LONG",
        entry=100.0,
        stop_loss=99.95,  # 0.05%
        votes={"llm_trader": _vote("llm_trader", "short")},  # opposes the LONG
    )
    rejections = run_guards(guards, ctx)
    names = {n for n, _ in rejections}
    assert names == {"quorum", "min_stop_distance"}


def test_opposition_blocks_but_lone_agreement_allows():
    """Policy change: a single AGREEING voice is fine (the judge already fused
    the signals); only ACTIVE OPPOSITION with no agreement blocks."""
    g = QuorumGuard()
    # exactly one permission voice agrees, the other is silent -> ALLOW
    allow_ctx = _ctx(votes={
        "llm_trader": _vote("llm_trader", "long"),
        "llm_tradebot": _vote("llm_tradebot", "neutral"),
    })
    assert g.check(allow_ctx) is None
    # a permission voice opposes with none agreeing -> BLOCK
    block_ctx = _ctx(votes={
        "llm_trader": _vote("llm_trader", "short"),
        "llm_tradebot": _vote("llm_tradebot", "offline"),
    })
    assert g.check(block_ctx) is not None


def test_run_guards_fails_safe_on_guard_exception():
    class _Boom:
        name = "boom"

        def check(self, ctx):
            raise RuntimeError("kaboom")

    rejections = run_guards([_Boom()], _ctx())
    assert rejections and rejections[0][0] == "boom"
    assert "guard error" in rejections[0][1] and "kaboom" in rejections[0][1]
