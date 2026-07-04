"""Judge prompt construction.

Split out of judge.py to keep that module focused on the trigger policy + API
call. Holds the system preamble, the per-source payload view, the current-price
helper, and the optional MEMORY / TIMEFRAMES sections plus the full prompt
assembly. The public builders are re-exported from judge for backward-compatible
imports.
"""
from __future__ import annotations

import json
from typing import Any

from sources.base import Vote

_SYSTEM_PREAMBLE = """You are a professional intraday futures trader judging {symbol} setups. You scalp and day-trade crypto perpetuals; you survive on selectivity, asymmetric risk-reward, and trading the RIGHT playbook for the current regime. You are NOT a permabear who stands aside in every chop -- a range is a tradeable regime, not an excuse to do nothing. Three independent systems report to you:
  1. LLM technical analyst (llm_trader: indicators + chart structure) -- a TREND/STRUCTURE voice.
  2. Multi-agent quant bot (llm_tradebot: per-timeframe trend/oscillator scores + ML) -- its higher-TF trend is a TREND/STRUCTURE voice.
  3. Order-flow imbalance detector (orderflow: footprint stacks + delta, per timeframe) -- a TRIGGER/TIMING voice, NOT a directional vote.

Run a PERMISSION -> SCORE -> TRIGGER cascade, fronted by a REGIME ROUTER. Do NOT demand that all three sources agree; the trend voices grant direction, order flow only times the entry.

STEP 0 -- REGIME ROUTER (classify, then pick the playbook; set `regime` and `playbook`):
  - TREND (ADX > 25, or clear directional higher-TF structure): use the TREND PLAYBOOK -- pullback-to-VWAP/MA continuation, or breakout-retest, IN the trend direction.
  - CHOP (ADX < 20, compression, price oscillating in a range): use the MEAN-REVERSION PLAYBOOK -- FADE range extremes / Bollinger-Keltner band touches back toward the mid. Chop is NOT "stand aside by default"; it is "switch to the reversion playbook." A clean fade at a range edge in chop is a real, tradeable setup.
  - TRANSITION (ADX ~20-25, no clear structure, no clean range edge): only here is standing aside the right call.

STEP 1 -- PERMISSION + DIRECTION (the trend/structure voices):
  llm_trader and llm_tradebot's higher-TF trend GRANT the direction. This is your main directional input. In TREND, direction = the trend. In CHOP, direction = the fade side dictated by which range extreme price is testing.

STEP 2 -- SETUP SCORE (0..100, a SCORE, not a pass/fail gate):
  Score setup quality from confluence: indicator alignment, proximity to a real level (S/R, VWAP, band, imbalance shelf), and multi-timeframe agreement. A higher score earns more entry_conviction and size; a low score lowers them. It does not by itself veto.

STEP 3 -- TRIGGER / TIMING (order flow):
  Order-flow delta / stacked imbalance TIMES the entry in the permitted direction. Order-flow DISAGREEMENT with the trend+setup direction means "NO TRIGGER YET / WAIT" -- it does NOT veto or flip the trade. Order flow must NEVER by itself flip or veto a trend+setup-supported trade; at most it delays it (lower entry_conviction, say "waiting for flow to confirm").

TWO-PHASE OUTPUT:
  Phase 1 -- Is there a tradeable setup in EITHER playbook (trend continuation OR range fade)? yes/no.
  Phase 2 -- Only if yes: score entry_conviction and set level-derived entry/stop/targets. If no, it's a no-trade: return direction FLAT but still fill directional_bias informatively.
  flat_confidence is computed INDEPENDENTLY (how sure you'd be that standing aside is right) and NEVER suppresses a real setup.

CALIBRATION (you are overconfident by default -- anchor your numbers):
  - directional_bias: -100..+100. Sign = side (positive long, negative short), magnitude = strength of the directional read. Set this BEFORE the act/flat decision; it stays informative even on a FLAT.
  - entry_conviction: 0..100, conviction to ENTER NOW. Below {act_threshold} is a no-trade (return FLAT). THIS is what gates a trade -- not directional_bias, not flat_confidence.
  - flat_confidence: 0..100, how confident you are that standing aside is correct. Informational only.
  - win_probability: 0..1, honest calibrated P(first target hit before stop). Anchor it: a ~1.5R setup needs win_probability > 0.40 to be +EV after ~0.35% round-trip fees. Do not inflate.
  - Compute risk_reward from YOUR OWN entry/stop_loss/take_profit_1 arithmetic. R:R floor for scalps is ~{rr_floor} (NOT 2.0); prefer higher, but do not demand 2.0+.

OUTPUT RULES:
  - NEVER invent price levels. Derive entry / stop_loss / take_profit ONLY from the sources' own levels (key_levels, support/resistance, order params, stacked-imbalance prices, VWAP, band edges, current price).
  - Stops go BEYOND the structure that invalidates the idea (swing point, range edge, band), never at an arbitrary tight distance inside noise.
  - If you cannot set honest levels, return them null and risk_reward null (which means FLAT).
  - position_size_pct: suggested % of normal size (0-100); scale with setup score -- full size for high-score with-trend or clean range fades, half or less for marginal/partially-confirmed setups.
  - regime: "trend" | "chop" | "transition". playbook: "trend" | "mean_reversion" | "none".
  - rationale: 3-6 sentences walking the cascade (regime -> permission/direction -> setup score -> trigger), citing WHICH sources drove the call.
  - invalidation: the concrete price/condition that kills the thesis.
  - disagreements: where the sources conflict (note explicitly when order flow merely lacks a trigger vs. truly opposes).
  - tf_alignment: ONE short line reading the multi-timeframe section, e.g. "1h up, 15m pullback holding, 5m reclaim -- with-trend long" or "range-bound, price at upper band -- fade short".
"""


def _payload_for_source(vote: Vote) -> dict[str, Any]:
    """Compact, JSON-safe view of one source for the prompt."""
    return {
        "direction": vote.direction,
        "confidence": round(vote.confidence, 3),
        "age_seconds": (
            round(vote.age_seconds, 1) if vote.age_seconds is not None else None
        ),
        "summary": vote.detail,
        "detail": vote.extra,
    }


def current_price(votes: dict[str, Vote]) -> float | None:
    """Best-effort current price: tradebot market.price, else orderflow close."""
    tb = votes.get("llm_tradebot")
    if tb is not None:
        price = tb.extra.get("market_price")
        if isinstance(price, (int, float)):
            return float(price)
    of = votes.get("orderflow")
    if of is not None:
        close = of.extra.get("close")
        if isinstance(close, (int, float)):
            return float(close)
    return None


def build_memory_section(memory: dict[str, Any] | None) -> str:
    """Render the optional MEMORY block from empirical system performance.

    `memory` may carry: recent_trades (list of compact dicts), scorecards
    (per-voice summary), lessons (list of active lesson texts). Returns an empty
    string when there is nothing to show (no closed trades, no lessons, no
    scorecard data) so the prompt is unchanged on a cold start.
    """
    if not memory:
        return ""
    recent = memory.get("recent_trades") or []
    scorecards = memory.get("scorecards") or []
    lessons = memory.get("lessons") or []
    if not recent and not scorecards and not lessons:
        return ""
    parts: list[str] = [
        "\n=== MEMORY (this system's actual measured performance) ===",
        "Weigh these empirical results when judging; they reflect this system's "
        "actual measured performance.",
    ]
    if recent:
        parts.append("\nLast closed positions:")
        for t in recent:
            parts.append(
                f"  - {t.get('direction')} conv={t.get('conviction')} "
                f"outcome={t.get('outcome')} R={t.get('r_multiple')} "
                f"regime={t.get('regime')} | {t.get('context_line', '')}".rstrip(" |")
            )
    if scorecards:
        parts.append("\nPer-voice scorecards (hit rate overall / current regime):")
        for sc in scorecards:
            parts.append(
                f"  - {sc.get('source')}: overall {sc.get('hit_rate')}% "
                f"(n={sc.get('resolved')}), regime {sc.get('regime')} "
                f"{sc.get('regime_hit_rate')}%"
            )
    if lessons:
        parts.append("\nActive lessons (learned rules):")
        for i, text in enumerate(lessons, start=1):
            parts.append(f"  {i}. {text}")
    return "\n".join(parts) + "\n"


def _tradebot_tf_trends(votes: dict[str, Vote]) -> dict[str, Any]:
    """Pull the tradebot per-timeframe trend scores (trend_1h/15m/5m) from its
    vote_details, if present. Empty dict when unavailable."""
    tb = votes.get("llm_tradebot")
    if tb is None:
        return {}
    vd = tb.extra.get("vote_details")
    if not isinstance(vd, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("trend_1h", "trend_30m", "trend_15m", "trend_5m", "trend_1m"):
        if key in vd and vd[key] is not None:
            out[key] = vd[key]
    return out


def build_timeframes_section(
    tf_summaries: list[dict[str, Any]] | None,
    votes: dict[str, Vote],
) -> str:
    """Render the TIMEFRAMES block: per-TF order-flow read + tradebot trends.

    `tf_summaries` is a list of dicts from orderflow_tf.TfSummary.to_dict().
    Returns an empty string when there is nothing to show so the prompt is
    unchanged on a cold start / orderflow outage with no tradebot trends."""
    summaries = tf_summaries or []
    usable = [s for s in summaries if s.get("status") == "ok"]
    trends = _tradebot_tf_trends(votes)
    if not usable and not trends:
        return ""
    parts: list[str] = [
        "\n=== TIMEFRAMES (multi-timeframe order-flow + trend) ===",
        "Use these to judge alignment across timeframes. Order-flow delta/stack "
        "is per latest closed candle of that interval; trend_* are the quant "
        "bot's per-timeframe trend scores (-100..100).",
    ]
    if usable:
        parts.append("\nOrder-flow by timeframe:")
        for s in usable:
            delta = s.get("delta")
            delta_s = f"{delta:+.2f}" if isinstance(delta, (int, float)) else "n/a"
            parts.append(
                f"  - {s.get('timeframe')}: delta={delta_s} "
                f"vol={s.get('total_volume')} close={s.get('close')} "
                f"buy_stack={s.get('buy_stack')} sell_stack={s.get('sell_stack')}"
            )
    if trends:
        parts.append("\nQuant-bot trend scores by timeframe:")
        for key, val in trends.items():
            parts.append(f"  - {key.replace('trend_', '')}: {val}")
    return "\n".join(parts) + "\n"


# Defaults for the calibration knobs interpolated into the preamble. Kept in
# sync with config.yaml judge.act_threshold / judge.rr_floor; build_prompt
# accepts explicit overrides so the live config drives the prompt.
_DEFAULT_ACT_THRESHOLD = 50.0
_DEFAULT_RR_FLOOR = 1.3


def build_prompt(
    votes: dict[str, Vote],
    symbol: str,
    price: float | None,
    memory: dict[str, Any] | None = None,
    tf_summaries: list[dict[str, Any]] | None = None,
    act_threshold: float = _DEFAULT_ACT_THRESHOLD,
    rr_floor: float = _DEFAULT_RR_FLOOR,
) -> str:
    """System-style preamble + each source's full payload as labeled JSON.

    When `memory` carries data, a MEMORY section (recent trades, per-voice
    scorecards, active lessons) is inserted after the preamble. When
    `tf_summaries` (or tradebot per-TF trends) are present, a TIMEFRAMES section
    is inserted so the judge can read multi-timeframe alignment.

    `act_threshold` / `rr_floor` parameterise the calibration block so the live
    judge config (act_threshold, rr_floor) drives the prompt rather than a hard
    constant.
    """
    preamble = _SYSTEM_PREAMBLE.format(
        symbol=symbol,
        act_threshold=f"{act_threshold:g}",
        rr_floor=f"{rr_floor:g}",
    )
    labels = {
        "llm_trader": "SOURCE 1 - LLM technical analyst (llm_trader)",
        "llm_tradebot": "SOURCE 2 - Multi-agent quant bot (llm_tradebot)",
        "orderflow": "SOURCE 3 - Order-flow imbalance detector (orderflow)",
    }
    blocks: list[str] = [preamble]
    memory_block = build_memory_section(memory)
    if memory_block:
        blocks.append(memory_block)
    tf_block = build_timeframes_section(tf_summaries, votes)
    if tf_block:
        blocks.append(tf_block)
    blocks.append(f"\nSYMBOL: {symbol}")
    price_str = f"{price}" if price is not None else "unknown"
    blocks.append(f"CURRENT PRICE: {price_str}\n")
    for key, label in labels.items():
        vote = votes.get(key)
        if vote is None:
            payload: dict[str, Any] = {"direction": "offline", "detail": {}}
        else:
            payload = _payload_for_source(vote)
        blocks.append(
            f"=== {label} ===\n"
            + json.dumps(payload, ensure_ascii=False, default=str, indent=2)
        )
    blocks.append(
        "\nReturn ONLY the JSON object matching the required schema. "
        "Do not wrap it in markdown."
    )
    return "\n".join(blocks)
