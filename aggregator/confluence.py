"""Confluence engine: combine per-source votes into an alert state.

Pure functions over the list of (already staleness-decayed) votes. No I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sources.base import Vote

AlertLevel = str  # "none" | "alert" | "strong"


@dataclass(frozen=True)
class Confluence:
    direction: str            # long / short / neutral
    level: AlertLevel         # none / alert / strong
    agree_count: int          # sources agreeing on `direction`
    online_count: int         # non-offline sources
    score: float              # weighted agreement score (0..1 of online weight)
    sizing_note: str          # informational only
    votes: list[Vote] = field(default_factory=list)


def evaluate(
    votes: list[Vote],
    weights: dict[str, float],
    alert_min_agree: int,
    strong_min_agree: int,
) -> Confluence:
    online = [v for v in votes if v.direction != "offline"]
    online_count = len(online)

    # Tally weighted votes per direction (neutral does not count toward a side).
    tally: dict[str, float] = {"long": 0.0, "short": 0.0}
    count: dict[str, int] = {"long": 0, "short": 0}
    for v in online:
        if v.direction in ("long", "short"):
            w = weights.get(v.source, 1.0)
            tally[v.direction] += w
            count[v.direction] += 1

    # Winning direction by weight, tie-break by count.
    if tally["long"] == 0 and tally["short"] == 0:
        direction = "neutral"
    elif tally["long"] > tally["short"]:
        direction = "long"
    elif tally["short"] > tally["long"]:
        direction = "short"
    else:
        direction = "long" if count["long"] >= count["short"] else "short"

    agree_count = count[direction] if direction in count else 0
    total_online_weight = sum(weights.get(v.source, 1.0) for v in online) or 1.0
    score = (tally[direction] / total_online_weight) if direction in tally else 0.0

    level: AlertLevel = "none"
    sizing = "no aligned signal"
    if direction in ("long", "short"):
        if agree_count >= strong_min_agree and agree_count == online_count and online_count >= strong_min_agree:
            level = "strong"
            sizing = "full size (3/3 agreement) — informational only"
        elif agree_count >= alert_min_agree:
            level = "alert"
            sizing = f"half size ({agree_count}/{online_count} agreement) — informational only"
        else:
            level = "none"
            sizing = f"only {agree_count} agree (need {alert_min_agree})"

    return Confluence(
        direction=direction,
        level=level,
        agree_count=agree_count,
        online_count=online_count,
        score=round(score, 3),
        sizing_note=sizing,
        votes=votes,
    )
