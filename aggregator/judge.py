"""LLM Judge: the aggregated trading indicator.

A single Gemini call that receives the three sources' full payloads + the
current price and returns ONE position assessment (direction, conviction,
entry/SL/TP, R:R, rationale, invalidation, disagreements).

Design notes
------------
* The API key is read at runtime from the llm-tradebot .env (config.read_gemini_key);
  it is never stored in config or hardcoded here.
* Raw REST via httpx with Gemini's JSON mode (response_mime_type +
  response_schema) -- no google-genai dependency.
* Resilient by construction: any API error / timeout / schema mismatch keeps the
  last good result with stale=True and an error string; the judge never raises
  out of evaluate(), so the polling loop can never crash on a Gemini hiccup.
* Trigger policy: run when (a) any source's direction changed since the last
  judge run, or (b) the last result is older than max_age_seconds -- but never
  more often than min_interval_seconds. All sources offline -> skipped.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from config import JudgeCfg, read_gemini_key
from sources.base import Vote

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

_VALID_DIRECTIONS = {"LONG", "SHORT", "FLAT"}

# Gemini structured-output schema for the judge verdict.
#
# Conviction is DECOUPLED into three independent signals:
#   * directional_bias  -100..+100 (sign = side, magnitude = strength), set
#     BEFORE the act/flat decision.
#   * entry_conviction  0..100 -- conviction to ENTER NOW. THIS gates a trade.
#   * flat_confidence   0..100 -- confidence that standing aside is correct.
#                       Informational ONLY; it NEVER gates a trade.
# `conviction` is kept as a backward-compatible alias of entry_conviction.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["LONG", "SHORT", "FLAT"]},
        "directional_bias": {"type": "number"},
        "entry_conviction": {"type": "number"},
        "flat_confidence": {"type": "number"},
        "win_probability": {"type": "number"},
        "regime": {"type": "string"},
        "playbook": {"type": "string"},
        "entry": {"type": "number", "nullable": True},
        "stop_loss": {"type": "number", "nullable": True},
        "take_profit_1": {"type": "number", "nullable": True},
        "take_profit_2": {"type": "number", "nullable": True},
        "risk_reward": {"type": "number", "nullable": True},
        "position_size_pct": {"type": "number"},
        "timeframe": {"type": "string"},
        "tf_alignment": {"type": "string"},
        "rationale": {"type": "string"},
        "invalidation": {"type": "string"},
        "disagreements": {"type": "string"},
    },
    "required": [
        "direction",
        "directional_bias",
        "entry_conviction",
        "flat_confidence",
        "win_probability",
        "regime",
        "playbook",
        "position_size_pct",
        "timeframe",
        "tf_alignment",
        "rationale",
        "invalidation",
        "disagreements",
    ],
}


@dataclass(frozen=True)
class JudgeResult:
    """One judge verdict (or an empty/error default)."""

    status: str  # "ok" | "error" | "no_data" | "starting"
    direction: str = "FLAT"  # LONG | SHORT | FLAT
    # Decoupled conviction signals (see _RESPONSE_SCHEMA notes):
    directional_bias: float = 0.0  # -100..+100; sign=side, magnitude=strength
    entry_conviction: float = 0.0  # 0..100; conviction to ENTER NOW -> gates a trade
    flat_confidence: float = 0.0  # 0..100; confidence in standing aside (informational)
    win_probability: float | None = None  # 0..1 calibrated P(target before stop)
    regime: str = ""  # trend | chop | transition (judge's regime-router read)
    playbook: str = ""  # trend | mean_reversion | none
    # Backward-compatible alias of entry_conviction so existing dashboard/tracker
    # references keep working. The tracker's open decision uses entry_conviction.
    conviction: float = 0.0
    entry: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    risk_reward: float | None = None
    position_size_pct: float = 0.0
    timeframe: str = ""
    tf_alignment: str = ""
    rationale: str = ""
    invalidation: str = ""
    disagreements: str = ""
    model: str = ""
    produced_at: float = 0.0  # epoch seconds of the underlying API call
    stale: bool = False
    error: str = ""
    call_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = {
            "status": self.status,
            "direction": self.direction,
            "directional_bias": self.directional_bias,
            "entry_conviction": self.entry_conviction,
            "flat_confidence": self.flat_confidence,
            "win_probability": self.win_probability,
            "regime": self.regime,
            "playbook": self.playbook,
            "conviction": self.conviction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "risk_reward": self.risk_reward,
            "position_size_pct": self.position_size_pct,
            "timeframe": self.timeframe,
            "tf_alignment": self.tf_alignment,
            "rationale": self.rationale,
            "invalidation": self.invalidation,
            "disagreements": self.disagreements,
            "model": self.model,
            "produced_at": self.produced_at,
            "stale": self.stale,
            "error": self.error,
            "call_count": self.call_count,
        }
        if self.produced_at:
            d["age_seconds"] = max(0.0, time.time() - self.produced_at)
        else:
            d["age_seconds"] = None
        return d


# Prompt construction lives in judge_prompt (keeps this module focused on the
# trigger policy + API call). Re-exported for backward-compatible imports.
from judge_prompt import (  # noqa: E402
    build_memory_section,
    build_prompt,
    build_timeframes_section,
    current_price,
)

__all__ = [
    "Judge",
    "JudgeResult",
    "build_memory_section",
    "build_prompt",
    "build_timeframes_section",
    "current_price",
    "parse_response",
]

def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_response(
    raw_text: str, model: str, call_count: int, produced_at: float
) -> JudgeResult:
    """Parse Gemini's JSON-mode text into a JudgeResult.

    Raises ValueError on schema mismatch so the caller can keep the last good
    result and surface the error.
    """
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("judge response is not a JSON object")
    direction = str(data.get("direction") or "").strip().upper()
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(f"invalid direction: {direction!r}")

    # entry_conviction is the gating signal; accept the legacy `conviction`
    # key as a fallback so an older-style response still parses.
    entry_conv = _coerce_float(data.get("entry_conviction"))
    if entry_conv is None:
        entry_conv = _coerce_float(data.get("conviction"))
    if entry_conv is None:
        raise ValueError("missing/invalid entry_conviction")
    entry_conv = max(0.0, min(100.0, entry_conv))

    directional_bias = _coerce_float(data.get("directional_bias"))
    directional_bias = (
        max(-100.0, min(100.0, directional_bias)) if directional_bias is not None else 0.0
    )
    flat_conf = _coerce_float(data.get("flat_confidence"))
    flat_conf = max(0.0, min(100.0, flat_conf)) if flat_conf is not None else 0.0
    win_prob = _coerce_float(data.get("win_probability"))
    if win_prob is not None:
        win_prob = max(0.0, min(1.0, win_prob))

    return JudgeResult(
        status="ok",
        direction=direction,
        directional_bias=directional_bias,
        entry_conviction=entry_conv,
        flat_confidence=flat_conf,
        win_probability=win_prob,
        regime=str(data.get("regime") or ""),
        playbook=str(data.get("playbook") or ""),
        conviction=entry_conv,  # backward-compat alias
        entry=_coerce_float(data.get("entry")),
        stop_loss=_coerce_float(data.get("stop_loss")),
        take_profit_1=_coerce_float(data.get("take_profit_1")),
        take_profit_2=_coerce_float(data.get("take_profit_2")),
        risk_reward=_coerce_float(data.get("risk_reward")),
        position_size_pct=max(0.0, min(100.0, _coerce_float(data.get("position_size_pct")) or 0.0)),
        timeframe=str(data.get("timeframe") or ""),
        tf_alignment=str(data.get("tf_alignment") or ""),
        rationale=str(data.get("rationale") or ""),
        invalidation=str(data.get("invalidation") or ""),
        disagreements=str(data.get("disagreements") or ""),
        model=model,
        produced_at=produced_at,
        stale=False,
        error="",
        call_count=call_count,
    )


def _extract_text(body: dict[str, Any]) -> str:
    """Pull the model text out of a generateContent response."""
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("no candidates in Gemini response")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    text = "".join(texts).strip()
    if not text:
        raise ValueError("empty text in Gemini response")
    return text


@dataclass
class Judge:
    """Stateful judge: owns the trigger policy, call count, and last result."""

    cfg: JudgeCfg
    symbol: str
    last_result: JudgeResult = field(
        default_factory=lambda: JudgeResult(status="starting")
    )
    # Optional: called at evaluate() time to supply the MEMORY section data
    # (recent trades / scorecards / lessons). None -> no memory section.
    memory_provider: Callable[[], dict[str, Any]] | None = None
    # Optional: called at evaluate() time to supply per-timeframe order-flow
    # summaries (list of TfSummary dicts). None -> no TIMEFRAMES section.
    tf_provider: Callable[[], list[dict[str, Any]]] | None = None
    _last_call_ts: float = 0.0
    _last_dirs: dict[str, str] = field(default_factory=dict)
    call_count: int = 0

    @property
    def last_call_ts(self) -> float:
        """Epoch seconds of the most recent actual Gemini call (0.0 if never).

        Exposed so callers (e.g. instrument.last_judge_ts) can report the real
        last-judge timestamp instead of a wall-clock stand-in value.
        """
        return self._last_call_ts

    def _online(self, votes: dict[str, Vote]) -> list[Vote]:
        return [v for v in votes.values() if v.direction != "offline"]

    def _carry_forward_online_dirs(self, votes: dict[str, Vote]) -> dict[str, str]:
        """Per-source last known ONLINE direction.

        For each source that is currently online, take its live direction; for a
        source that just went offline, carry forward the direction it last held
        while online (from self._last_dirs). This is what change detection
        compares against so an offline<->online flap (with the same underlying
        direction) is NOT counted as a change.
        """
        result = dict(self._last_dirs)
        for k, v in votes.items():
            direction = str(v.direction)
            if direction != "offline":
                result[k] = direction
            # offline -> leave the carried-forward last-online direction intact
        return result

    def should_run(self, votes: dict[str, Vote], now: float | None = None) -> tuple[bool, str]:
        """Trigger policy. Returns (run?, reason)."""
        now = time.time() if now is None else now
        if not self.cfg.enabled:
            return False, "disabled"
        if not self._online(votes):
            return False, "no data (all sources offline)"
        # Rate floor -- never more often than min_interval_seconds.
        if self._last_call_ts and (now - self._last_call_ts) < self.cfg.min_interval_seconds:
            return False, "rate-limited"
        # (a) any ONLINE source's direction changed. Offline transitions are
        # excluded: a source flapping offline<->online (common on file/db
        # liveness blips) would otherwise look like a direction change every
        # tick and storm the judge. We compare each source's last *online*
        # direction (carried forward across offline gaps) against the prior
        # recorded set, so an offline blip with no real change is a no-op.
        carried = self._carry_forward_online_dirs(votes)
        if carried != self._last_dirs and self._last_dirs:
            return True, "source direction changed"
        # First run (no prior online dirs recorded).
        if not self._last_dirs:
            return True, "first run"
        # (b) staleness ceiling
        if not self._last_call_ts or (now - self._last_call_ts) >= self.cfg.max_age_seconds:
            return True, "stale"
        return False, "no trigger"

    def _call_gemini(self, prompt: str, key: str) -> str:
        url = _ENDPOINT.format(model=self.cfg.model, key=key)
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
                "temperature": 0.4,
            },
        }
        with httpx.Client(timeout=self.cfg.timeout_seconds) as client:
            resp = client.post(url, json=body)
            if resp.status_code >= 400:
                detail = resp.text[:300].replace("\n", " ")
                raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")
            return _extract_text(resp.json())

    def evaluate(self, votes: dict[str, Vote], now: float | None = None) -> JudgeResult:
        """Run a judge call if the trigger policy allows; else return last.

        Never raises: any failure keeps the previous result with stale=True and
        an error string.
        """
        now = time.time() if now is None else now
        run, reason = self.should_run(votes, now)
        # Track each source's last ONLINE direction (carry forward across
        # offline gaps) for next comparison -- matches should_run's logic so an
        # offline flap never registers as a change.
        new_dirs = self._carry_forward_online_dirs(votes)

        if not run:
            if reason == "no data (all sources offline)":
                self.last_result = JudgeResult(
                    status="no_data",
                    error="all sources offline",
                    call_count=self.call_count,
                )
            self._last_dirs = new_dirs
            return self.last_result

        key = read_gemini_key(self.cfg.api_key_env_path)
        if not key:
            self._last_dirs = new_dirs
            self.last_result = self._stale_with_error(
                "GEMINI_API_KEY not found in tradebot .env"
            )
            return self.last_result

        price = current_price(votes)
        memory: dict[str, Any] | None = None
        if self.memory_provider is not None:
            try:
                memory = self.memory_provider()
            except Exception:  # memory is best-effort; never block a verdict
                memory = None
        tf_summaries: list[dict[str, Any]] | None = None
        if self.tf_provider is not None:
            try:
                tf_summaries = self.tf_provider()
            except Exception:  # TF summaries are best-effort; never block
                tf_summaries = None
        prompt = build_prompt(
            votes,
            self.symbol,
            price,
            memory,
            tf_summaries,
            act_threshold=self.cfg.act_threshold,
            rr_floor=self.cfg.rr_floor,
        )
        self._last_dirs = new_dirs
        self._last_call_ts = now
        self.call_count += 1
        try:
            text = self._call_gemini(prompt, key)
            result = parse_response(text, self.cfg.model, self.call_count, now)
            self.last_result = result
            return result
        except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            self.last_result = self._stale_with_error(f"{type(exc).__name__}: {exc}")
            return self.last_result

    def _stale_with_error(self, error: str) -> JudgeResult:
        """Keep the last good verdict but mark it stale and attach the error."""
        prev = self.last_result
        return JudgeResult(
            status="error",
            direction=prev.direction,
            directional_bias=prev.directional_bias,
            entry_conviction=prev.entry_conviction,
            flat_confidence=prev.flat_confidence,
            win_probability=prev.win_probability,
            regime=prev.regime,
            playbook=prev.playbook,
            conviction=prev.conviction,
            entry=prev.entry,
            stop_loss=prev.stop_loss,
            take_profit_1=prev.take_profit_1,
            take_profit_2=prev.take_profit_2,
            risk_reward=prev.risk_reward,
            position_size_pct=prev.position_size_pct,
            timeframe=prev.timeframe,
            tf_alignment=prev.tf_alignment,
            rationale=prev.rationale,
            invalidation=prev.invalidation,
            disagreements=prev.disagreements,
            model=self.cfg.model,
            produced_at=prev.produced_at,
            stale=True,
            error=error,
            call_count=self.call_count,
        )
