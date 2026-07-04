"""Alert decision + dedupe/cooldown logic, decoupled from I/O.

Decides whether a new confluence state warrants a notification:
  * fire on a NEW alert/strong-alert
  * fire on a direction FLIP while in an alert state
  * suppress repeats of the same direction within the cooldown window
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from confluence import Confluence


@dataclass
class AlertState:
    last_direction: str = "neutral"
    last_level: str = "none"
    last_fired_direction: str = "none"
    last_fired_ts: float = 0.0


@dataclass(frozen=True)
class AlertDecision:
    should_fire: bool
    reason: str
    title: str
    body: str


def decide(
    conf: Confluence,
    state: AlertState,
    symbol: str,
    cooldown_seconds: float,
    now: float | None = None,
) -> AlertDecision:
    now = time.time() if now is None else now
    is_alerting = conf.level in ("alert", "strong")

    if not is_alerting:
        return AlertDecision(False, "no-alert", "", "")

    flipped = (
        state.last_level in ("alert", "strong")
        and conf.direction != state.last_direction
        and conf.direction in ("long", "short")
    )
    new_alert = state.last_level not in ("alert", "strong")

    within_cooldown = (
        conf.direction == state.last_fired_direction
        and (now - state.last_fired_ts) < cooldown_seconds
    )

    if within_cooldown and not flipped:
        return AlertDecision(False, "cooldown", "", "")

    if not (new_alert or flipped):
        # Same alert state, same direction, cooldown expired -> re-affirm once.
        if within_cooldown:
            return AlertDecision(False, "cooldown", "", "")

    label = "STRONG ALERT" if conf.level == "strong" else "ALERT"
    arrow = "LONG ▲" if conf.direction == "long" else "SHORT ▼"
    reason = "flip" if flipped else ("new" if new_alert else "reaffirm")
    title = f"{label}: {symbol} {arrow}"
    body = (
        f"{conf.agree_count}/{conf.online_count} sources agree "
        f"(score {conf.score:.2f}). {conf.sizing_note}"
    )
    return AlertDecision(True, reason, title, body)
