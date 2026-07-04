"""
Multi-Period Parser Agent
=========================

Summarizes multi-timeframe signals (1h/15m/5m) and four-layer status.
Designed to feed a concise, structured context to the Decision Agent.
"""

from typing import Dict, Any

from src.utils.logger import log


class MultiPeriodParserAgent:
    """Multi-Period Parser Agent (non-LLM)."""

    name = "multi_period_agent"

    @staticmethod
    def _score_to_sign(score: float, pos: float, neg: float) -> int:
        if score >= pos:
            return 1
        if score <= neg:
            return -1
        return 0

    def analyze(
        self,
        quant_analysis: Dict[str, Any],
        four_layer_result: Dict[str, Any] = None,
        semantic_analyses: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        trend = quant_analysis.get("trend", {}) or {}
        oscillator = quant_analysis.get("oscillator", {}) or {}
        sentiment = quant_analysis.get("sentiment", {}) or {}

        t_1h = float(trend.get("trend_1h_score", 0) or 0)
        t_15m = float(trend.get("trend_15m_score", 0) or 0)
        t_5m = float(trend.get("trend_5m_score", 0) or 0)

        sign_1h = self._score_to_sign(t_1h, 25, -25)
        sign_15m = self._score_to_sign(t_15m, 18, -18)
        sign_5m = self._score_to_sign(t_5m, 12, -12)

        if sign_1h == sign_15m == sign_5m and sign_1h != 0:
            aligned = True
            alignment_reason = f"All timeframes aligned ({'bull' if sign_1h > 0 else 'bear'})"
        elif sign_1h == sign_15m and sign_1h != 0:
            aligned = True
            alignment_reason = f"1h+15m aligned ({'bull' if sign_1h > 0 else 'bear'})"
        else:
            aligned = False
            alignment_reason = (
                f"Misaligned (1h:{sign_1h}, 15m:{sign_15m}, 5m:{sign_5m}) - wait for 1h"
            )

        bias = "BULLISH" if sign_1h > 0 else ("BEARISH" if sign_1h < 0 else "NEUTRAL")

        four_layer_result = four_layer_result or {}
        layer_flags = {
            "L1": bool(four_layer_result.get("layer1_pass")),
            "L2": bool(four_layer_result.get("layer2_pass")),
            "L3": bool(four_layer_result.get("layer3_pass")),
            "L4": bool(four_layer_result.get("layer4_pass")),
        }

        final_action = (four_layer_result.get("final_action") or "wait").upper()

        summary = (
            f"Align={alignment_reason} | Trend 1h/15m/5m "
            f"{t_1h:+.0f}/{t_15m:+.0f}/{t_5m:+.0f} | "
            f"4-Layer {final_action} ("
            f"L1:{'Y' if layer_flags['L1'] else 'N'},"
            f"L2:{'Y' if layer_flags['L2'] else 'N'},"
            f"L3:{'Y' if layer_flags['L3'] else 'N'},"
            f"L4:{'Y' if layer_flags['L4'] else 'N'})"
        )

        result = {
            "alignment": aligned,
            "alignment_reason": alignment_reason,
            "bias": bias,
            "trend_scores": {
                "trend_1h": t_1h,
                "trend_15m": t_15m,
                "trend_5m": t_5m
            },
            "oscillator_scores": {
                "osc_1h": float(oscillator.get("osc_1h_score", 0) or 0),
                "osc_15m": float(oscillator.get("osc_15m_score", 0) or 0),
                "osc_5m": float(oscillator.get("osc_5m_score", 0) or 0)
            },
            "sentiment_score": float(sentiment.get("total_sentiment_score", 0) or 0),
            "four_layer": {
                "final_action": final_action,
                "layer_pass": layer_flags
            },
            "semantic_analyses": semantic_analyses or {},
            "summary": summary
        }

        log.info(f"[MultiPeriodParser] {summary}")
        return result
