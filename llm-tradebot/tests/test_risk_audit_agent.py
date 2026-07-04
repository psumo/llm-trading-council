"""
Unit tests for RiskAuditAgent hard veto and conflict gates.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.risk_audit_agent import RiskAuditAgent


def _base_decision(action: str) -> dict:
    return {
        "symbol": "BTCUSDT",
        "action": action,
        "entry_price": 100.0,
        "stop_loss": 98.0 if action == "open_long" else 102.0,
        "take_profit": 103.0 if action == "open_long" else 97.0,
        "quantity": 1.0,
        "leverage": 5.0,
        "confidence": 82.0,
        "regime": {"regime": "trending_up" if action == "open_long" else "trending_down"},
        "position": {"position_pct": 25.0, "location": "lower"},
        "trend_scores": {
            "trend_1h_score": 45.0 if action == "open_long" else -45.0,
            "trend_15m_score": 20.0 if action == "open_long" else -20.0,
            "trend_5m_score": 10.0 if action == "open_long" else -10.0,
        },
        "oscillator_scores": {"osc_1h_score": -20.0, "osc_15m_score": -15.0, "osc_5m_score": -10.0},
        "position_1h": {"allow_long": True, "allow_short": True, "position_pct": 35.0, "location": "lower"},
    }


def _audit(decision: dict):
    agent = RiskAuditAgent()
    return asyncio.run(
        agent.audit_decision(
            decision=decision,
            current_position=None,
            account_balance=10_000.0,
            current_price=100.0,
            atr_pct=2.0,
        )
    )


def test_blocks_open_long_when_position_1h_disallows_long():
    decision = _base_decision("open_long")
    decision["position_1h"]["allow_long"] = False
    decision["position_1h"]["location"] = "upper"
    decision["position_1h"]["position_pct"] = 78.0

    result = _audit(decision)

    assert result.passed is False
    assert "allow_long=False" in (result.blocked_reason or "")


def test_blocks_open_short_when_position_1h_disallows_short():
    decision = _base_decision("open_short")
    decision["position_1h"]["allow_short"] = False
    decision["position_1h"]["location"] = "lower"
    decision["position_1h"]["position_pct"] = 22.0

    result = _audit(decision)

    assert result.passed is False
    assert "allow_short=False" in (result.blocked_reason or "")


def test_blocks_sideways_multitimeframe_conflict():
    decision = _base_decision("open_long")
    decision["confidence"] = 80.0
    decision["regime"] = {"regime": "Sideways (Consolidation)"}
    decision["trend_scores"] = {
        "trend_1h_score": -45.0,
        "trend_15m_score": -20.0,
        "trend_5m_score": 30.0,
    }

    result = _audit(decision)

    assert result.passed is False
    assert "多周期趋势冲突" in (result.blocked_reason or "")


def test_allows_sideways_conflict_with_very_high_confidence():
    decision = _base_decision("open_long")
    decision["confidence"] = 91.0
    decision["regime"] = {"regime": "Sideways (Consolidation)"}
    decision["trend_scores"] = {
        "trend_1h_score": -30.0,
        "trend_15m_score": 18.0,
        "trend_5m_score": 25.0,
    }

    result = _audit(decision)

    assert result.passed is True
    assert result.warnings is not None
    assert any("多周期趋势冲突" in warning for warning in result.warnings)


def test_blocks_open_long_on_long_loss_streak():
    decision = _base_decision("open_long")
    decision["confidence"] = 72.0
    decision["symbol_long_loss_streak"] = 3
    decision["symbol_long_recent_trades"] = 3
    decision["symbol_long_recent_pnl"] = -12.0

    result = _audit(decision)

    assert result.passed is False
    assert "多头连续亏损" in (result.blocked_reason or "")


def test_blocks_open_short_on_short_recent_pnl_drawdown():
    decision = _base_decision("open_short")
    decision["confidence"] = 70.0
    decision["symbol_short_loss_streak"] = 1
    decision["symbol_short_recent_trades"] = 4
    decision["symbol_short_recent_pnl"] = -50.0
    decision["oscillator_scores"] = {"osc_1h_score": -35.0, "osc_15m_score": -30.0, "osc_5m_score": -25.0}

    result = _audit(decision)

    assert result.passed is False
    assert "暂停空单" in (result.blocked_reason or "")


def test_allows_breakdown_override_when_short_disallowed_but_strong_trend():
    decision = _base_decision("open_short")
    decision["confidence"] = 93.0
    decision["regime"] = {"regime": "Trending Down"}
    decision["position_1h"] = {
        "allow_long": True,
        "allow_short": False,
        "position_pct": 18.0,
        "location": "support",
    }
    decision["trend_scores"] = {
        "trend_1h_score": -70.0,
        "trend_15m_score": -40.0,
        "trend_5m_score": -20.0,
    }
    decision["oscillator_scores"] = {"osc_1h_score": -30.0, "osc_15m_score": -25.0, "osc_5m_score": -20.0}

    result = _audit(decision)

    assert result.passed is True
    assert result.warnings is not None
    assert any("突破放行" in warning for warning in result.warnings)


def test_does_not_override_when_sideways_even_with_high_confidence():
    decision = _base_decision("open_short")
    decision["confidence"] = 95.0
    decision["regime"] = {"regime": "Sideways (Consolidation)"}
    decision["position_1h"] = {
        "allow_long": True,
        "allow_short": False,
        "position_pct": 12.0,
        "location": "support",
    }
    decision["trend_scores"] = {
        "trend_1h_score": -75.0,
        "trend_15m_score": -35.0,
        "trend_5m_score": -15.0,
    }

    result = _audit(decision)

    assert result.passed is False
    assert "allow_short=False" in (result.blocked_reason or "")


def test_allows_short_with_continuation_guard_when_setup_is_weak():
    decision = _base_decision("open_short")
    decision["confidence"] = 60.0
    decision["regime"] = {"regime": "Trending Down"}
    decision["position"] = {"position_pct": 78.0, "location": "upper"}
    decision["position_1h"] = {"allow_long": True, "allow_short": True, "position_pct": 78.0, "location": "upper"}
    decision["trend_scores"] = {
        "trend_1h_score": -62.0,
        "trend_15m_score": -24.0,
        "trend_5m_score": -8.0,
    }
    decision["oscillator_scores"] = {"osc_1h_score": -12.0, "osc_15m_score": -9.0, "osc_5m_score": -6.0}
    decision["four_layer"] = {
        "layer1_pass": True,
        "layer2_pass": True,
        "layer3_pass": True,
        "layer4_pass": True,
        "final_action": "short",
        "trigger_pattern": "soft_momentum",
        "adx": 31.0,
    }

    result = _audit(decision)

    assert result.passed is True
    assert result.warnings is not None
    assert any("延续信号" in warning for warning in result.warnings)


def test_continuation_guard_disabled_in_sideways_regime():
    decision = _base_decision("open_short")
    decision["confidence"] = 60.0
    decision["regime"] = {"regime": "Sideways (Consolidation)"}
    decision["position"] = {"position_pct": 78.0, "location": "upper"}
    decision["position_1h"] = {"allow_long": True, "allow_short": True, "position_pct": 78.0, "location": "upper"}
    decision["trend_scores"] = {
        "trend_1h_score": -62.0,
        "trend_15m_score": -24.0,
        "trend_5m_score": -8.0,
    }
    decision["oscillator_scores"] = {"osc_1h_score": -12.0, "osc_15m_score": -9.0, "osc_5m_score": -6.0}
    decision["four_layer"] = {
        "layer1_pass": True,
        "layer2_pass": True,
        "layer3_pass": True,
        "layer4_pass": True,
        "final_action": "short",
        "trigger_pattern": "soft_momentum",
        "adx": 31.0,
    }

    result = _audit(decision)

    assert result.passed is False
    assert "空头信号未达到强共振条件" in (result.blocked_reason or "")
