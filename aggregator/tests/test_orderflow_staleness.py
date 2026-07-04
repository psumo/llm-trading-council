"""Higher-TF staleness guard for the orderflow voice."""
from datetime import datetime, timedelta, timezone

from sources.orderflow import _tf_is_stale


def test_fresh_candle_not_stale():
    now = datetime.now(timezone.utc)
    assert _tf_is_stale(now - timedelta(minutes=30), "1h") is False  # within 2.5x


def test_old_candle_is_stale():
    now = datetime.now(timezone.utc)
    assert _tf_is_stale(now - timedelta(hours=3), "1h") is True       # > 2.5x 1h
    assert _tf_is_stale(now - timedelta(days=2), "1h") is True


def test_15m_boundary():
    now = datetime.now(timezone.utc)
    assert _tf_is_stale(now - timedelta(minutes=20), "15m") is False  # < 37.5m
    assert _tf_is_stale(now - timedelta(minutes=45), "15m") is True   # > 37.5m


def test_naive_datetime_treated_utc():
    naive_old = datetime.utcnow() - timedelta(hours=5)
    assert _tf_is_stale(naive_old, "1h") is True


def test_non_datetime_not_stale():
    assert _tf_is_stale(None, "1h") is False
    assert _tf_is_stale("not-a-date", "1h") is False
