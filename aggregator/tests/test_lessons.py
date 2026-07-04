"""Lessons store round-trip: add, retire, persist/reload, stale auto-retire,
and the reflection trigger-policy (is_due) including the 'not due with 0 trades'
case the live verification relies on.
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ReflectionCfg  # noqa: E402
from lessons import LessonsStore  # noqa: E402
from reflection import is_due  # noqa: E402


def _refl_cfg(**kw) -> ReflectionCfg:
    base = dict(
        enabled=True,
        min_new_trades=5,
        min_interval_hours=24.0,
        max_lesson_age_days=30.0,
        lessons_path="unused.json",
    )
    base.update(kw)
    return ReflectionCfg(**base)


# ---- add / retire round-trip ------------------------------------------


def test_add_and_active(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    assert store.active() == []
    le = store.add("when regime=chop and agree<2, longs lost 4/5 -> avoid")
    assert len(store.active()) == 1
    assert le.status == "active"
    assert le.score == 0.0


def test_retire_by_id(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    le = store.add("rule A")
    store.add("rule B")
    assert store.retire(le.id) is True
    active_texts = [x.text for x in store.active()]
    assert active_texts == ["rule B"]
    # Retiring an unknown / already-retired id is a no-op.
    assert store.retire(le.id) is False
    assert store.retire("nonexistent") is False


def test_persist_reload(tmp_path) -> None:
    path = tmp_path / "lessons.json"
    store = LessonsStore.load(path)
    le = store.add("persisted rule")
    store.set_meta(datetime.now(timezone.utc).isoformat(), 7)
    assert store.save() is True

    reloaded = LessonsStore.load(path)
    assert [x.text for x in reloaded.active()] == ["persisted rule"]
    assert reloaded.closed_at_last_reflection == 7
    assert reloaded.lessons[0].id == le.id


def test_retire_stale(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    fresh = store.add("fresh rule")
    old = store.add("old rule")
    # Backdate the 'old' lesson's last_evaluated beyond the 30-day window.
    long_ago = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    store.lessons = [
        x if x.id != old.id else type(x)(
            id=x.id, text=x.text, created_at=long_ago,
            score=x.score, last_evaluated=long_ago, status="active",
        )
        for x in store.lessons
    ]
    retired = store.retire_stale(30.0)
    assert retired == [old.id]
    assert [x.text for x in store.active()] == ["fresh rule"]
    assert fresh.id in {x.id for x in store.active()}


# ---- reflection trigger policy ----------------------------------------


def test_is_due_not_due_with_zero_trades(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    due, reason = is_due(_refl_cfg(), store, closed_count=0)
    assert due is False
    assert "not due" in reason
    assert "0 new trades" in reason


def test_is_due_disabled(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    due, reason = is_due(_refl_cfg(enabled=False), store, closed_count=100)
    assert due is False
    assert reason == "disabled"


def test_is_due_true_when_enough_new_trades(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    # No prior reflection -> interval gate passes; 5 >= min_new_trades(5).
    due, reason = is_due(_refl_cfg(), store, closed_count=5)
    assert due is True
    assert "due:" in reason


def test_is_due_interval_gate(tmp_path) -> None:
    store = LessonsStore.load(tmp_path / "lessons.json")
    now = datetime.now(timezone.utc)
    store.last_reflection_at = (now - timedelta(hours=1)).isoformat()
    store.closed_at_last_reflection = 0
    # 10 new trades but only 1h since last reflection (need 24h).
    due, reason = is_due(_refl_cfg(), store, closed_count=10, now=now.timestamp())
    assert due is False
    assert "since last" in reason
