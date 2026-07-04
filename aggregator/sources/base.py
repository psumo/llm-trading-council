"""Shared vote types for all signal sources.

A source never raises out of its poll(): on any failure it returns an
offline Vote so the aggregator loop can never be crashed by a dead source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["long", "short", "neutral", "offline"]


@dataclass(frozen=True)
class Vote:
    """A single source's current opinion.

    direction  : long / short / neutral / offline
    confidence : 0.0..1.0 (best-effort; 0 when unknown/offline)
    age_seconds: seconds since the underlying signal was produced; None when
                 unknown or offline.
    detail     : short human-readable snippet (reasoning / status).
    """

    source: str
    direction: Direction = "offline"
    confidence: float = 0.0
    age_seconds: float | None = None
    detail: str = ""
    extra: dict = field(default_factory=dict)

    def decayed(self, staleness_seconds: float) -> "Vote":
        """Return a copy whose direction decays to neutral when the signal is
        older than staleness_seconds. Offline/neutral pass through unchanged."""
        if self.direction in ("offline", "neutral"):
            return self
        if self.age_seconds is not None and self.age_seconds > staleness_seconds:
            return Vote(
                source=self.source,
                direction="neutral",
                confidence=self.confidence,
                age_seconds=self.age_seconds,
                detail=f"stale ({int(self.age_seconds)}s > {int(staleness_seconds)}s); was {self.direction}",
                extra=self.extra,
            )
        return self


def offline(source: str, reason: str) -> Vote:
    """Convenience constructor for an offline vote."""
    return Vote(source=source, direction="offline", confidence=0.0, age_seconds=None, detail=reason)
