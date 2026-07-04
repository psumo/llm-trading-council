"""Tests for the scorecard resolver outcome logic + the full record/resolve
round-trip against a temp SQLite db.

classify_outcome is the pure core (long/short/flat); the Scorecards class is
exercised end-to-end to confirm rows are written only on direction CHANGE and
resolved once the horizon elapses.
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ScorecardsCfg  # noqa: E402
from scorecards import Scorecards, classify_outcome  # noqa: E402


def _cfg(horizon=60.0, min_move=0.1, window=50) -> ScorecardsCfg:
    return ScorecardsCfg(
        enabled=True,
        horizon_minutes=horizon,
        min_move_pct=min_move,
        window=window,
    )


# ---- pure outcome logic -----------------------------------------------


def test_classify_outcome_long() -> None:
    assert classify_outcome("long", 0.5, 0.1) == "correct"   # rose enough
    assert classify_outcome("long", -0.5, 0.1) == "wrong"    # fell
    assert classify_outcome("long", 0.05, 0.1) == "flat"     # below min move


def test_classify_outcome_short() -> None:
    assert classify_outcome("short", -0.5, 0.1) == "correct"  # fell -> short right
    assert classify_outcome("short", 0.5, 0.1) == "wrong"     # rose -> short wrong
    assert classify_outcome("short", -0.05, 0.1) == "flat"


def test_classify_outcome_flat_band_is_symmetric() -> None:
    assert classify_outcome("long", 0.099, 0.1) == "flat"
    assert classify_outcome("short", -0.099, 0.1) == "flat"
    assert classify_outcome("long", 0.1, 0.1) == "correct"


# ---- record only on direction change ----------------------------------


def test_record_only_on_direction_change(tmp_path) -> None:
    sc = Scorecards(_cfg(), str(tmp_path / "vs.db"))
    dirs = {"llm_trader": "long", "llm_tradebot": "neutral", "orderflow": "short"}
    confs = {"llm_trader": 0.8, "llm_tradebot": 0.0, "orderflow": 0.6}
    # First tick: trader long + orderflow short are scorable -> 2 rows.
    assert sc.record(dirs, confs, 100.0, "trend") == 2
    # Same directions again -> no new rows.
    assert sc.record(dirs, confs, 101.0, "trend") == 0
    # Trader flips to short -> 1 new row.
    dirs2 = {**dirs, "llm_trader": "short"}
    assert sc.record(dirs2, confs, 102.0, "chop") == 1
    sc.close()


# ---- resolve after horizon --------------------------------------------


def test_resolve_after_horizon(tmp_path) -> None:
    sc = Scorecards(_cfg(horizon=60.0, min_move=0.1), str(tmp_path / "vs.db"))
    sc.record({"llm_trader": "long"}, {"llm_trader": 0.8}, 100.0, "trend")

    # Not yet due (no time elapsed) -> nothing resolves.
    assert sc.resolve(100.5) == 0

    # Backdate the row's ts past the horizon, then resolve at a higher price.
    old = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    sc._conn.execute("UPDATE voice_signals SET ts = ?", (old,))
    sc._conn.commit()
    assert sc.resolve(101.0) == 1  # +1% move -> long correct

    snap = sc.snapshot()
    trader = snap["voices"]["llm_trader"]
    assert trader["resolved"] == 1
    assert trader["correct"] == 1
    assert trader["hit_rate"] == 100.0
    assert trader["by_regime"]["trend"]["hit_rate"] == 100.0
    sc.close()


def test_resolve_flat_excluded_from_hit_rate(tmp_path) -> None:
    sc = Scorecards(_cfg(horizon=60.0, min_move=0.1), str(tmp_path / "vs.db"))
    sc.record({"orderflow": "long"}, {"orderflow": 0.6}, 100.0, "chop")
    old = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    sc._conn.execute("UPDATE voice_signals SET ts = ?", (old,))
    sc._conn.commit()
    # Tiny move (+0.05%) is below min_move -> flat, excluded from hit rate.
    assert sc.resolve(100.05) == 1
    trader = sc.snapshot()["voices"]["orderflow"]
    assert trader["resolved"] == 0   # no decided signals
    assert trader["hit_rate"] is None
    sc.close()
