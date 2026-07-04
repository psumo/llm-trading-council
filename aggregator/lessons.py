"""Lessons store: the judge's learned, conditional rules (lessons.json).

A lesson is a short conditional rule the reflection pass distilled from the
closed-trade journal, e.g. "when regime=chop and agree_count<2, longs lost
4/5 -> avoid". Lessons are scored and retired over time.

File shape (JSON):
  {
    "meta": {"last_reflection_at": ISO|null, "closed_at_last_reflection": int},
    "lessons": [
      {"id": str, "text": str, "created_at": ISO, "score": float,
       "last_evaluated": ISO|null, "status": "active"|"retired"}
    ]
  }

All reads/writes are atomic-ish (write to a temp file then replace) and never
raise out of the caller: a corrupt/missing file degrades to an empty store.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Lesson:
    id: str
    text: str
    created_at: str
    score: float = 0.0
    last_evaluated: str | None = None
    status: str = "active"  # "active" | "retired"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "created_at": self.created_at,
            "score": self.score,
            "last_evaluated": self.last_evaluated,
            "status": self.status,
        }


def _lesson_from_dict(d: dict[str, Any]) -> Lesson | None:
    text = str(d.get("text") or "").strip()
    if not text:
        return None
    return Lesson(
        id=str(d.get("id") or uuid.uuid4().hex[:12]),
        text=text,
        created_at=str(d.get("created_at") or _now_iso()),
        score=float(d.get("score") or 0.0),
        last_evaluated=d.get("last_evaluated"),
        status=str(d.get("status") or "active"),
    )


@dataclass
class LessonsStore:
    """Owns lessons.json: load, query active lessons, add/retire, meta tracking."""

    path: Path
    lessons: list[Lesson] = field(default_factory=list)
    last_reflection_at: str | None = None
    closed_at_last_reflection: int = 0
    # Guards every mutation of `lessons`/meta. The reflection pass mutates this
    # store from one thread while the judge's memory provider reads active()
    # from another; without the lock that read can iterate a list mid-mutation.
    # repr/compare excluded so dataclass equality/printing is unaffected.
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    @classmethod
    def load(cls, path: str | Path) -> "LessonsStore":
        p = Path(path)
        store = cls(path=p)
        if not p.is_file():
            p.parent.mkdir(parents=True, exist_ok=True)
            store.save()  # seed an empty store
            return store
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return store
        if not isinstance(data, dict):
            return store
        raw_meta = data.get("meta")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        store.last_reflection_at = meta.get("last_reflection_at")
        store.closed_at_last_reflection = int(meta.get("closed_at_last_reflection") or 0)
        raw_lessons = data.get("lessons")
        if isinstance(raw_lessons, list):
            for item in raw_lessons:
                if isinstance(item, dict):
                    lesson = _lesson_from_dict(item)
                    if lesson is not None:
                        store.lessons.append(lesson)
        return store

    def active(self) -> list[Lesson]:
        """Return a SNAPSHOT copy of the active lessons (safe to iterate while
        another thread mutates the store). Lessons are frozen dataclasses, so
        the shallow copy is fully immutable."""
        with self._lock:
            return [le for le in self.lessons if le.status == "active"]

    def add(self, text: str, score: float = 0.0) -> Lesson:
        lesson = Lesson(
            id=uuid.uuid4().hex[:12],
            text=text.strip()[:200],
            created_at=_now_iso(),
            score=score,
            last_evaluated=_now_iso(),
            status="active",
        )
        with self._lock:
            self.lessons.append(lesson)
        return lesson

    def retire(self, lesson_id: str) -> bool:
        """Mark a lesson retired by id. Returns True when one was changed."""
        changed = False
        new_lessons: list[Lesson] = []
        with self._lock:
            for le in self.lessons:
                if le.id == lesson_id and le.status == "active":
                    new_lessons.append(
                        Lesson(
                            id=le.id,
                            text=le.text,
                            created_at=le.created_at,
                            score=le.score,
                            last_evaluated=_now_iso(),
                            status="retired",
                        )
                    )
                    changed = True
                else:
                    new_lessons.append(le)
            self.lessons = new_lessons
        return changed

    def rescore(self, lesson_id: str, score: float) -> None:
        new_lessons: list[Lesson] = []
        with self._lock:
            for le in self.lessons:
                if le.id == lesson_id:
                    new_lessons.append(
                        Lesson(
                            id=le.id,
                            text=le.text,
                            created_at=le.created_at,
                            score=score,
                            last_evaluated=_now_iso(),
                            status=le.status,
                        )
                    )
                else:
                    new_lessons.append(le)
            self.lessons = new_lessons

    def retire_stale(self, max_age_days: float) -> list[str]:
        """Retire active lessons older than max_age_days not re-evaluated
        within that window. Returns the ids retired."""
        retired: list[str] = []
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400.0
        # active() takes a snapshot under the lock; retire() re-locks per id
        # (RLock is reentrant, so a future nested call would also be safe).
        for le in self.active():
            ref = le.last_evaluated or le.created_at
            ts = _parse_ts(ref)
            if ts is not None and ts.timestamp() < cutoff:
                if self.retire(le.id):
                    retired.append(le.id)
        return retired

    def set_meta(self, last_reflection_at: str, closed_count: int) -> None:
        with self._lock:
            self.last_reflection_at = last_reflection_at
            self.closed_at_last_reflection = closed_count

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "meta": {
                    "last_reflection_at": self.last_reflection_at,
                    "closed_at_last_reflection": self.closed_at_last_reflection,
                },
                "lessons": [le.to_dict() for le in self.lessons],
            }

    def save(self) -> bool:
        """Persist atomically. Returns False on I/O error (never raises)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8"
            )
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
