"""
Unit tests for ExecutionEngine action protocol compatibility.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.execution.engine import ExecutionEngine


class _DummyClient:
    def __init__(self):
        self.orders = []

    def cancel_all_orders(self, symbol):
        return True

    def place_market_order(self, symbol, side, quantity, reduce_only=False, position_side=None):
        self.orders.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "reduce_only": reduce_only,
                "position_side": position_side,
            }
        )
        return {"symbol": symbol, "side": side, "qty": quantity}


class _DummyRisk:
    pass


def test_close_position_normalizes_to_directional_close():
    engine = ExecutionEngine(_DummyClient(), _DummyRisk())
    result = engine.execute_decision(
        decision={"symbol": "BTCUSDT", "action": "close_position"},
        account_info={},
        position_info={"position_amt": -0.2},
        current_price=100.0,
    )
    assert result["success"] is True
    assert result["action"] == "close_short"


def test_directional_close_mismatch_is_blocked():
    engine = ExecutionEngine(_DummyClient(), _DummyRisk())
    result = engine.execute_decision(
        decision={"symbol": "BTCUSDT", "action": "close_long"},
        account_info={},
        position_info={"position_amt": -0.2},
        current_price=100.0,
    )
    assert result["success"] is False
    assert result["action"] == "close_long"


def test_wait_action_is_noop_success():
    engine = ExecutionEngine(_DummyClient(), _DummyRisk())
    result = engine.execute_decision(
        decision={"symbol": "ETHUSDT", "action": "wait"},
        account_info={},
        position_info=None,
        current_price=200.0,
    )
    assert result["success"] is True
    assert result["message"] == "观望，不执行操作"


def test_legacy_add_position_still_routed_for_compatibility():
    engine = ExecutionEngine(_DummyClient(), _DummyRisk())
    result = engine.execute_decision(
        decision={"symbol": "ETHUSDT", "action": "add_position"},
        account_info={},
        position_info=None,
        current_price=200.0,
    )
    assert result["success"] is False
    assert result["action"] == "add_position"
