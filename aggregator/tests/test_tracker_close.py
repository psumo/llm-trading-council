"""Pure-function tests for the tracker close logic and R/balance math.

Covers the four close outcomes (stop-loss, take-profit, judge flip, timeout)
for both a LONG and a SHORT position, plus the realized R / pnl / balance
update arithmetic. No I/O -- everything operates on Position dataclasses.

Run from the aggregator dir:
    .venv/Scripts/python.exe -m pytest tests/test_tracker_close.py -v
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker_models import (  # noqa: E402
    Position,
    decide_close,
    realized_close,
    unrealized_r,
)


def _long() -> Position:
    # entry 100, stop 90 -> risk distance 10; TP1 120 -> +2R target.
    return Position(
        id=1,
        opened_at="2026-06-12T00:00:00+00:00",
        direction="LONG",
        conviction=70.0,
        symbol="BTCUSDT",
        entry=100.0,
        stop_loss=90.0,
        take_profit_1=120.0,
        take_profit_2=None,
        risk_reward=2.0,
        rationale="test",
        risk_usd=10.0,
    )


def _short() -> Position:
    # entry 100, stop 110 -> risk distance 10; TP1 80 -> +2R target.
    return Position(
        id=2,
        opened_at="2026-06-12T00:00:00+00:00",
        direction="SHORT",
        conviction=70.0,
        symbol="ETHUSDT",
        entry=100.0,
        stop_loss=110.0,
        take_profit_1=80.0,
        take_profit_2=None,
        risk_reward=2.0,
        rationale="test",
        risk_usd=10.0,
    )


# ---- unrealized_r ------------------------------------------------------


def test_unrealized_r_long() -> None:
    pos = _long()
    assert unrealized_r(pos, 110.0) == 1.0  # +10 / 10 risk
    assert unrealized_r(pos, 90.0) == -1.0
    assert unrealized_r(pos, 100.0) == 0.0


def test_unrealized_r_short() -> None:
    pos = _short()
    assert unrealized_r(pos, 90.0) == 1.0  # price fell 10 -> +1R
    assert unrealized_r(pos, 110.0) == -1.0
    assert unrealized_r(pos, 100.0) == 0.0


# ---- LONG close paths --------------------------------------------------


def test_long_hits_stop_loss() -> None:
    pos = _long()
    d = decide_close(pos, 89.0, "LONG", 0, 55, 0.1, 12)
    assert d == ("loss", 90.0)  # exits at the stop level


def test_long_hits_take_profit() -> None:
    pos = _long()
    d = decide_close(pos, 125.0, "LONG", 0, 55, 0.1, 12)
    assert d == ("win", 120.0)  # exits at TP1 level


def test_long_judge_flip() -> None:
    pos = _long()
    # price still in range, but judge flips to SHORT with conviction >= min.
    d = decide_close(pos, 105.0, "SHORT", 80, 55, 0.1, 12)
    assert d == ("flip", 105.0)


def test_long_flip_ignored_below_min_conviction() -> None:
    pos = _long()
    d = decide_close(pos, 105.0, "SHORT", 40, 55, 0.1, 12)
    assert d is None  # conviction too low; stay open


def test_long_timeout() -> None:
    pos = _long()
    d = decide_close(pos, 105.0, "LONG", 0, 55, 13.0, 12)
    assert d == ("timeout", 105.0)


def test_long_stays_open() -> None:
    pos = _long()
    d = decide_close(pos, 105.0, "LONG", 80, 55, 1.0, 12)
    assert d is None


# ---- SHORT close paths -------------------------------------------------


def test_short_hits_stop_loss() -> None:
    pos = _short()
    d = decide_close(pos, 111.0, "SHORT", 0, 55, 0.1, 12)
    assert d == ("loss", 110.0)


def test_short_hits_take_profit() -> None:
    pos = _short()
    d = decide_close(pos, 75.0, "SHORT", 0, 55, 0.1, 12)
    assert d == ("win", 80.0)


def test_short_judge_flip() -> None:
    pos = _short()
    d = decide_close(pos, 95.0, "LONG", 90, 55, 0.1, 12)
    assert d == ("flip", 95.0)


def test_short_timeout() -> None:
    pos = _short()
    d = decide_close(pos, 95.0, "SHORT", 0, 55, 20.0, 12)
    assert d == ("timeout", 95.0)


# ---- realized close math + balance updates -----------------------------


def test_realized_close_long_win() -> None:
    pos = _long()
    closed = realized_close(pos, 120.0, "win", "2026-06-12T01:00:00+00:00")
    assert closed.r_multiple == 2.0  # +20 / 10
    assert closed.pnl_pct == 20.0  # (120-100)/100
    assert closed.pnl_usd == 20.0  # 2R * $10 risk
    assert not closed.is_open


def test_realized_close_long_loss() -> None:
    pos = _long()
    closed = realized_close(pos, 90.0, "loss", "2026-06-12T01:00:00+00:00")
    assert closed.r_multiple == -1.0
    assert closed.pnl_pct == -10.0
    assert closed.pnl_usd == -10.0


def test_realized_close_short_win() -> None:
    pos = _short()
    closed = realized_close(pos, 80.0, "win", "2026-06-12T01:00:00+00:00")
    assert closed.r_multiple == 2.0  # (100-80)/10
    # price fell 20% from entry; in the trade's favour pnl_pct is positive.
    assert closed.pnl_pct == 20.0
    assert closed.pnl_usd == 20.0


def test_realized_close_short_loss() -> None:
    pos = _short()
    closed = realized_close(pos, 110.0, "loss", "2026-06-12T01:00:00+00:00")
    assert closed.r_multiple == -1.0
    assert closed.pnl_pct == -10.0
    assert closed.pnl_usd == -10.0


def test_balance_update_sequence() -> None:
    """Simulate a win then a loss; balance reflects pnl_usd of each."""
    balance = 1000.0
    win = realized_close(_long(), 120.0, "win", "2026-06-12T01:00:00+00:00")
    balance += win.pnl_usd or 0.0
    assert balance == 1020.0
    loss = realized_close(_short(), 110.0, "loss", "2026-06-12T02:00:00+00:00")
    balance += loss.pnl_usd or 0.0
    assert balance == 1010.0


def test_excursion_tracking() -> None:
    pos = _long()
    pos = pos.with_excursion(115.0)  # +1.5R favourable
    pos = pos.with_excursion(95.0)  # -0.5R adverse
    pos = pos.with_excursion(108.0)
    assert pos.max_favorable == 1.5
    assert pos.max_adverse == -0.5
    assert pos.last_price == 108.0
