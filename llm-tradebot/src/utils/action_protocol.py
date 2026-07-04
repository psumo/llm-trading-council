"""
Trading action protocol helpers.

Canonical actions:
- open_long / open_short
- close_long / close_short
- close_position (generic close when side is unknown)
- wait / hold
"""

from enum import Enum
from typing import Optional


class Action(str, Enum):
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    WAIT = "wait"
    HOLD = "hold"


OPEN_ACTIONS = frozenset({
    Action.OPEN_LONG.value,
    Action.OPEN_SHORT.value,
})

CLOSE_ACTIONS = frozenset({
    Action.CLOSE_LONG.value,
    Action.CLOSE_SHORT.value,
    "close_position",
})

PASSIVE_ACTIONS = frozenset({
    Action.WAIT.value,
    Action.HOLD.value,
})

VALID_ACTIONS = OPEN_ACTIONS | CLOSE_ACTIONS | PASSIVE_ACTIONS


def normalize_action(action: Optional[str], position_side: Optional[str] = None) -> str:
    """Normalize aliases to canonical action values."""
    raw = str(action or "").strip().lower()
    side = str(position_side or "").strip().lower()

    mapping = {
        "open_long": Action.OPEN_LONG.value,
        "long": Action.OPEN_LONG.value,
        "buy": Action.OPEN_LONG.value,
        "go_long": Action.OPEN_LONG.value,
        "open_short": Action.OPEN_SHORT.value,
        "short": Action.OPEN_SHORT.value,
        "sell": Action.OPEN_SHORT.value,
        "go_short": Action.OPEN_SHORT.value,
        "close_long": Action.CLOSE_LONG.value,
        "exit_long": Action.CLOSE_LONG.value,
        "close_short": Action.CLOSE_SHORT.value,
        "exit_short": Action.CLOSE_SHORT.value,
        "wait": Action.WAIT.value,
        "skip": Action.WAIT.value,
        "hold": Action.HOLD.value,
    }
    if raw in mapping:
        return mapping[raw]

    if raw in {"close", "exit", "close_position"}:
        if side in {"long", "open_long"}:
            return Action.CLOSE_LONG.value
        if side in {"short", "open_short"}:
            return Action.CLOSE_SHORT.value
        # Side unknown: keep generic close action, caller may resolve later.
        return "close_position"

    return Action.WAIT.value


def is_open_action(action: Optional[str]) -> bool:
    return normalize_action(action) in OPEN_ACTIONS


def is_close_action(action: Optional[str]) -> bool:
    return normalize_action(action) in CLOSE_ACTIONS


def is_long_action(action: Optional[str]) -> bool:
    return normalize_action(action) in {Action.OPEN_LONG.value, Action.CLOSE_LONG.value}


def is_short_action(action: Optional[str]) -> bool:
    return normalize_action(action) in {Action.OPEN_SHORT.value, Action.CLOSE_SHORT.value}


def is_passive_action(action: Optional[str]) -> bool:
    return normalize_action(action) in PASSIVE_ACTIONS
