"""Append-only event log (events.jsonl) plus an in-memory rolling buffer.

Every signal snapshot and alert is appended as one JSON line so the user can
later evaluate which voice was right. Writes are best-effort and never raise
out of the loop.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    def __init__(self, events_path: str, max_log_events: int):
        self.path = Path(events_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max_log_events)
        self._lock = threading.Lock()

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {"ts": _now_iso(), "type": event_type, **payload}
        with self._lock:
            self._buffer.append(record)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, default=str) + "\n")
            except OSError:
                # Disk error must not crash the loop; keep the in-memory copy.
                pass
        return record

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buffer)
