import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.trigger_detector_agent import TriggerDetector


def _df(rows):
    return pd.DataFrame(rows)


def test_breakout_uses_dynamic_volume_threshold():
    detector = TriggerDetector()
    df = _df(
        [
            {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 100.0},
            {"open": 100.5, "high": 101.5, "low": 100.0, "close": 101.2, "volume": 100.0},
            {"open": 101.2, "high": 102.0, "low": 100.8, "close": 101.8, "volume": 100.0},
            {"open": 101.8, "high": 102.7, "low": 101.1, "close": 102.2, "volume": 95.0},
        ]
    )

    res = detector.detect_breakout(df, direction="long")

    assert res["detected"]
    assert res["volume_ratio"] < 1.0
    assert res["volume_threshold"] <= 0.9


def test_breakout_sensitivity_changes_trigger_strictness():
    detector = TriggerDetector()
    df = _df(
        [
            {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 100.0},
            {"open": 100.5, "high": 101.5, "low": 100.0, "close": 101.2, "volume": 100.0},
            {"open": 101.2, "high": 102.0, "low": 100.8, "close": 101.8, "volume": 100.0},
            {"open": 101.8, "high": 103.0, "low": 101.8, "close": 102.3, "volume": 95.0},
        ]
    )
    loose = detector.detect_breakout(df, direction="long", sensitivity=0.9)
    strict = detector.detect_breakout(df, direction="long", sensitivity=1.1)

    assert loose["detected"]
    assert not strict["detected"]


def test_continuation_trigger_detected_for_trend_resume():
    detector = TriggerDetector()
    df = _df(
        [
            {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.3, "volume": 100.0},
            {"open": 100.3, "high": 100.7, "low": 100.1, "close": 100.6, "volume": 102.0},
            {"open": 100.6, "high": 101.1, "low": 100.4, "close": 100.9, "volume": 104.0},
            {"open": 100.9, "high": 101.4, "low": 100.7, "close": 101.2, "volume": 106.0},
            {"open": 101.2, "high": 101.8, "low": 101.0, "close": 101.6, "volume": 108.0},
            {"open": 101.6, "high": 101.7, "low": 101.2, "close": 101.4, "volume": 96.0},
            {"open": 101.4, "high": 101.9, "low": 101.3, "close": 101.7, "volume": 98.0},
            {"open": 101.7, "high": 102.4, "low": 101.6, "close": 102.2, "volume": 95.0},
        ]
    )

    res = detector.detect_trigger(df, direction="long")

    assert res["triggered"] is True
    assert res["pattern_type"] in {"breakout", "continuation"}


def test_rvol_fallback_does_not_trigger_on_tiny_chop_candles():
    detector = TriggerDetector()
    base = 100.0
    rows = []
    for i in range(12):
        open_p = base + (0.01 if i % 2 else -0.01)
        close_p = open_p + (0.01 if i % 2 else -0.01)
        rows.append(
            {
                "open": open_p,
                "high": max(open_p, close_p) + 0.01,
                "low": min(open_p, close_p) - 0.01,
                "close": close_p,
                "volume": 100.0,
            }
        )
    df = _df(rows)

    res = detector.detect_trigger(df, direction="long")

    assert res["triggered"] is False
