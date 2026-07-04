"""Judge reflection pass: distill lessons from the closed-trade journal.

A periodic, separate Gemini call (same model/key as the judge) that reviews the
full closed-trade journal with entry contexts and the current active lessons,
then returns JSON proposing lessons to add and lessons to retire (with reasons).

Trigger policy (all must hold):
  * reflection.enabled is true,
  * >= reflection.min_new_trades closed positions since the last reflection
    (tracked via lessons.json meta closed_at_last_reflection),
  * at least reflection.min_interval_hours since the last reflection.

Resilient by construction: any API/parse error is reported in the result and
the loop continues. Also auto-retires lessons older than max_lesson_age_days
that were not re-confirmed by this run.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from config import JudgeCfg, ReflectionCfg, read_gemini_key
from journal import build_journal
from lessons import LessonsStore
from tracker_models import Position

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lessons_to_add": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        "lessons_to_retire": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["lessons_to_add", "lessons_to_retire"],
}

_PREAMBLE = (
    "You are the REFLECTION analyst for an automated trading judge. You review "
    "this system's OWN closed paper trades (with the market conditions each was "
    "opened into) and the current learned lessons, then propose updates.\n\n"
    "Return JSON with:\n"
    "  lessons_to_add: NEW conditional rules, each <= 200 chars, phrased as "
    "'when X, Y happened N/M times -> rule'. Only propose a lesson with real "
    "empirical support in the trades shown. Do NOT duplicate an existing active "
    "lesson.\n"
    "  lessons_to_retire: ids of existing lessons the data now contradicts or "
    "that are no longer supported, each with a short reason.\n"
    "  summary: one sentence on what changed.\n"
    "Be conservative: if the sample is too small to justify a rule, return "
    "empty arrays. Ground every claim in the actual outcomes shown."
)


@dataclass(frozen=True)
class ReflectionResult:
    status: str  # "ok" | "not_due" | "error" | "disabled"
    reason: str = ""
    added: int = 0
    retired: int = 0
    auto_retired: int = 0
    summary: str = ""
    produced_at: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "added": self.added,
            "retired": self.retired,
            "auto_retired": self.auto_retired,
            "summary": self.summary,
            "produced_at": self.produced_at,
            "error": self.error,
        }


def _hours_since(iso: str | None, now: float) -> float | None:
    if not iso:
        return None
    text = iso.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt.timestamp()) / 3600.0)


def is_due(
    cfg: ReflectionCfg,
    store: LessonsStore,
    closed_count: int,
    now: float | None = None,
) -> tuple[bool, str]:
    """Pure trigger check. Returns (due?, human reason)."""
    now = time.time() if now is None else now
    if not cfg.enabled:
        return False, "disabled"
    new_trades = closed_count - store.closed_at_last_reflection
    if new_trades < cfg.min_new_trades:
        return False, (
            f"not due: {new_trades} new trades (need {cfg.min_new_trades})"
        )
    hrs = _hours_since(store.last_reflection_at, now)
    if hrs is not None and hrs < cfg.min_interval_hours:
        return False, (
            f"not due: {hrs:.1f}h since last (need {cfg.min_interval_hours}h)"
        )
    return True, f"due: {new_trades} new trades"


def build_prompt(closed: list[Position], store: LessonsStore) -> str:
    journal = build_journal(closed)
    active = store.active()
    lessons_block = (
        "\n".join(f"  [{le.id}] {le.text}" for le in active)
        if active
        else "  (none yet)"
    )
    payload = {
        "aggregates": journal["aggregates"],
        "trades": journal["trades"],
    }
    return (
        _PREAMBLE
        + "\n\n=== CURRENT ACTIVE LESSONS ===\n"
        + lessons_block
        + "\n\n=== CLOSED-TRADE JOURNAL (with entry contexts + conditional aggregates) ===\n"
        + json.dumps(payload, ensure_ascii=False, default=str, indent=2)
        + "\n\nReturn ONLY the JSON object. Do not wrap it in markdown."
    )


def _extract_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("no candidates in Gemini response")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    text = "".join(texts).strip()
    if not text:
        raise ValueError("empty text in Gemini response")
    return text


def parse_response(raw_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Parse the reflection JSON. Returns (to_add, to_retire, summary).

    Raises ValueError on a structurally invalid response so the caller can keep
    going and surface the error.
    """
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("reflection response is not a JSON object")
    raw_add = data.get("lessons_to_add")
    raw_retire = data.get("lessons_to_retire")
    to_add = [x for x in raw_add if isinstance(x, dict) and x.get("text")] if isinstance(raw_add, list) else []
    to_retire = [x for x in raw_retire if isinstance(x, dict) and x.get("id")] if isinstance(raw_retire, list) else []
    summary = str(data.get("summary") or "")
    return to_add, to_retire, summary


class Reflector:
    """Owns the reflection trigger policy and the Gemini call."""

    def __init__(self, cfg: ReflectionCfg, judge_cfg: JudgeCfg):
        self.cfg = cfg
        self.judge_cfg = judge_cfg

    def _call_gemini(self, prompt: str, key: str) -> str:
        url = _ENDPOINT.format(model=self.judge_cfg.model, key=key)
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
                "temperature": 0.3,
            },
        }
        with httpx.Client(timeout=self.judge_cfg.timeout_seconds) as client:
            resp = client.post(url, json=body)
            if resp.status_code >= 400:
                detail = resp.text[:300].replace("\n", " ")
                raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")
            return _extract_text(resp.json())

    def maybe_run(
        self,
        closed: list[Position],
        store: LessonsStore,
        now: float | None = None,
    ) -> ReflectionResult:
        """Run a reflection if due; persist lesson changes; never raises."""
        now = time.time() if now is None else now
        due, reason = is_due(self.cfg, store, len(closed), now)
        if not due:
            return ReflectionResult(
                status="disabled" if reason == "disabled" else "not_due",
                reason=reason,
            )

        key = read_gemini_key(self.judge_cfg.api_key_env_path)
        if not key:
            return ReflectionResult(
                status="error",
                reason=reason,
                error="GEMINI_API_KEY not found in tradebot .env",
            )

        prompt = build_prompt(closed, store)
        try:
            text = self._call_gemini(prompt, key)
            to_add, to_retire, summary = parse_response(text)
        except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return ReflectionResult(
                status="error",
                reason=reason,
                error=f"{type(exc).__name__}: {exc}",
            )

        added = 0
        for item in to_add:
            store.add(str(item["text"]))
            added += 1
        retired = 0
        for item in to_retire:
            if store.retire(str(item["id"])):
                retired += 1
        auto = store.retire_stale(self.cfg.max_lesson_age_days)
        store.set_meta(
            datetime.fromtimestamp(now, tz=timezone.utc).isoformat(), len(closed)
        )
        store.save()
        return ReflectionResult(
            status="ok",
            reason=reason,
            added=added,
            retired=retired,
            auto_retired=len(auto),
            summary=summary,
            produced_at=now,
        )
