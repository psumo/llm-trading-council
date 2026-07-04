"""Multi-timeframe order-flow summaries for the judge.

For a single symbol the judge wants a compact per-timeframe read of the latest
*closed* footprint candle: its delta, total volume, close, and stacked-imbalance
counts. This module queries footprint_candle WHERE interval=<tf> once per
configured timeframe and returns a JSON-able summary list.

It reuses the imbalance maths from sources.orderflow so the per-TF stacked
counts are computed identically to the live (1m) vote. Pure read path: any DB
failure degrades to an empty/`unavailable` summary for that timeframe and never
raises out of build_tf_summaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg

from sources.orderflow import _coerce_levels, _max_consecutive_imbalance, _tf_is_stale


@dataclass(frozen=True)
class TfSummary:
    """One timeframe's latest-closed-candle order-flow read."""

    timeframe: str
    status: str  # "ok" | "no_data" | "error"
    delta: float | None = None
    total_volume: float | None = None
    close: float | None = None
    buy_stack: int = 0
    sell_stack: int = 0
    age_seconds: float | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "status": self.status,
            "delta": self.delta,
            "total_volume": self.total_volume,
            "close": self.close,
            "buy_stack": self.buy_stack,
            "sell_stack": self.sell_stack,
            "age_seconds": self.age_seconds,
            "error": self.error,
        }


def _f(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _summarize_row(
    timeframe: str,
    row: tuple[Any, ...],
    tick: float,
    ratio: float,
) -> TfSummary:
    """Build a TfSummary from one footprint_candle row.

    Row columns: openTime, volumeDelta, priceLevels, close, volume.
    """
    open_time, volume_delta, price_levels, close, volume = row
    age: float | None = None
    if isinstance(open_time, datetime):
        if open_time.tzinfo is None:
            open_time = open_time.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - open_time).total_seconds())
    levels = _coerce_levels(price_levels)
    stack = _max_consecutive_imbalance(levels, tick, ratio)
    return TfSummary(
        timeframe=timeframe,
        status="ok",
        delta=_f(volume_delta),
        total_volume=_f(volume),
        close=_f(close),
        buy_stack=stack.buy_stack,
        sell_stack=stack.sell_stack,
        age_seconds=round(age, 1) if age is not None else None,
    )


class TfSummaryBuilder:
    """Queries footprint_candle per timeframe for one symbol."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        db: str,
        password: str | None,
        symbol: str,
        timeframes: list[str],
        tick_size: float,
        imbalance_ratio: float,
        timeout: float,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.db = db
        self.password = password
        self.symbol = symbol
        self.timeframes = list(timeframes)
        self.tick = tick_size
        self.ratio = imbalance_ratio
        self.timeout = timeout

    def _conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} user={self.user} "
            f"dbname={self.db} password={self.password or ''} "
            f"connect_timeout={int(max(1, self.timeout))}"
        )

    def build(self) -> list[TfSummary]:
        """Return one TfSummary per configured timeframe (order preserved).

        A missing password or DB failure yields an `error`/`no_data` summary for
        every timeframe; an individual timeframe with no rows yields `no_data`.
        Never raises.
        """
        if self.password is None:
            return [
                TfSummary(tf, "error", error="no DB password")
                for tf in self.timeframes
            ]
        try:
            with psycopg.connect(self._conninfo()) as conn:
                return [self._for_tf(conn, tf) for tf in self.timeframes]
        except psycopg.Error as exc:
            reason = str(exc).splitlines()[0] if str(exc) else "db error"
            return [TfSummary(tf, "error", error=reason) for tf in self.timeframes]

    def _for_tf(self, conn: "psycopg.Connection[Any]", tf: str) -> TfSummary:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''
                    SELECT "openTime", "volumeDelta", "priceLevels",
                           "close", "volume"
                    FROM footprint_candle
                    WHERE symbol = %s AND interval = %s
                    ORDER BY "openTime" DESC
                    LIMIT 1
                    ''',
                    (self.symbol, tf),
                )
                row = cur.fetchone()
        except psycopg.Error as exc:
            return TfSummary(tf, "error", error=str(exc).splitlines()[0])
        if row is None:
            return TfSummary(tf, "no_data", error="no candle for timeframe")
        if _tf_is_stale(row[0], tf):
            # Old candle (e.g. collector was down): tell the judge it's stale
            # rather than presenting a 2-day-old candle as current flow.
            return TfSummary(tf, "stale", error=f"latest {tf} candle is stale")
        return _summarize_row(tf, row, self.tick, self.ratio)


def summaries_to_dicts(summaries: list[TfSummary]) -> list[dict[str, Any]]:
    return [s.to_dict() for s in summaries]
