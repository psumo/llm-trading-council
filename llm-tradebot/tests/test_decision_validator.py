"""
Unit tests for decision validator action normalization contract.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.strategy.decision_validator import DecisionValidator


def test_validator_normalizes_open_alias_and_passes():
    validator = DecisionValidator()
    decision = {
        "symbol": "BTCUSDT",
        "action": "long",
        "reasoning": "Trend and momentum align.",
        "confidence": 80,
        "leverage": 2,
        "position_size_usd": 200.0,
        "current_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
    }
    is_valid, errors = validator.validate(decision)
    assert is_valid, errors
    assert decision["action"] == "open_long"


def test_validator_resolves_generic_close_by_position_side():
    validator = DecisionValidator()
    decision = {
        "symbol": "ETHUSDT",
        "action": "close_position",
        "position_side": "short",
        "reasoning": "Trend reversed against position.",
    }
    is_valid, errors = validator.validate(decision)
    assert is_valid, errors
    assert decision["action"] == "close_short"


def test_validator_downgrades_unsupported_action_to_wait():
    validator = DecisionValidator()
    decision = {
        "symbol": "SOLUSDT",
        "action": "add_position",
        "reasoning": "Unsupported in current runtime contract.",
    }
    is_valid, errors = validator.validate(decision)
    assert is_valid, errors
    assert decision["action"] == "wait"
