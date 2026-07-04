"""
Typed contracts for cross-stage agent data exchange.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.utils.action_protocol import normalize_action, is_open_action


@dataclass
class SuggestedTrade:
    """
    A normalized open-trade suggestion emitted by analysis stage and
    consumed by execution stage.
    """
    symbol: str
    action: str
    confidence: float
    order_params: Dict[str, Any]
    current_price: float = 0.0
    status: str = "suggested"

    @classmethod
    def from_cycle_result(cls, symbol: str, result: Dict[str, Any]) -> Optional["SuggestedTrade"]:
        if not isinstance(result, dict):
            return None
        if result.get("status") != "suggested":
            return None

        order_params = dict(result.get("order_params") or {})
        action = normalize_action(result.get("action") or order_params.get("action"))
        if not is_open_action(action):
            return None
        order_params["action"] = action

        try:
            confidence = float(result.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0

        try:
            current_price = float(result.get("current_price", 0) or 0)
        except (TypeError, ValueError):
            current_price = 0.0

        return cls(
            symbol=symbol,
            action=action,
            confidence=confidence,
            order_params=order_params,
            current_price=current_price,
            status="suggested",
        )

