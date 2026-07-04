"""Source 3: orderflow (order-flow voice), TimescaleDB / Postgres.

Reads recent footprint_candle rows and computes a long/short/neutral vote in
Python directly over the priceLevels jsonb -- no shelling out to node.

Logic
-----
priceLevels maps "<price>" -> {"volSumBid": n, "volSumAsk": n}.
Tick size (default 0.01) defines adjacent levels.

  * Buy imbalance at level P  : volSumBid(P) >= ratio * volSumAsk(P - tick)
  * Sell imbalance at level P : volSumAsk(P) >= ratio * volSumBid(P + tick)
  * Stacked imbalance         : >= stacked_levels consecutive imbalanced levels
                                in the same direction.

Combined with the sign of summed volumeDelta over the last lookback candles:
  * stacked-buy  AND delta > 0  -> long
  * stacked-sell AND delta < 0  -> short
  * stacked one way but delta disagrees, or no stack -> lean on delta sign if
    |delta| is meaningful, else neutral.

The Binance futures websocket is currently geo-blocked, so the table may be
empty or stale -- both degrade to offline (no fresh rows).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

from .base import Vote, offline


@dataclass(frozen=True)
class _StackResult:
    buy_stack: int
    sell_stack: int
    buy_levels: list[float]
    sell_levels: list[float]


def _coerce_levels(price_levels: object) -> dict[float, tuple[float, float]]:
    """Normalise the priceLevels jsonb into {price: (volSumBid, volSumAsk)}."""
    out: dict[float, tuple[float, float]] = {}
    if not isinstance(price_levels, dict):
        return out
    for k, v in price_levels.items():
        try:
            price = round(float(k), 8)
        except (TypeError, ValueError):
            continue
        if not isinstance(v, dict):
            continue
        try:
            bid = float(v.get("volSumBid", 0) or 0)
            ask = float(v.get("volSumAsk", 0) or 0)
        except (TypeError, ValueError):
            continue
        out[price] = (bid, ask)
    return out


# Seconds per interval label, for higher-TF staleness checks. A confirm candle
# older than _STALE_INTERVAL_MULT of its own interval is dropped (treated as
# missing) so a 2-day-old 1h candle can't masquerade as current order flow.
_INTERVAL_SECONDS: dict[str, float] = {
    "1m": 60.0, "5m": 300.0, "15m": 900.0, "30m": 1800.0,
    "1h": 3600.0, "2h": 7200.0, "4h": 14400.0, "1d": 86400.0,
}
_STALE_INTERVAL_MULT = 2.5


def _tf_is_stale(open_time: object, interval: str) -> bool:
    """True when a confirm-TF candle's openTime is too old to trust."""
    if not isinstance(open_time, datetime):
        return False
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=timezone.utc)
    span = _INTERVAL_SECONDS.get(interval)
    if span is None:
        return False
    age = (datetime.now(timezone.utc) - open_time).total_seconds()
    return age > span * _STALE_INTERVAL_MULT


def _max_consecutive_imbalance(
    levels: dict[float, tuple[float, float]], tick: float, ratio: float
) -> _StackResult:
    """Compute the longest run of consecutive buy / sell imbalanced levels.

    Also records every price level that was imbalanced (in either direction)
    so the dashboard can show *where* the stacking happened.
    """
    if not levels:
        return _StackResult(0, 0, [], [])
    sorted_prices = sorted(levels.keys())
    # Map for O(1) neighbour lookup keyed by rounded tick index.
    def idx(p: float) -> int:
        return round(p / tick)

    by_idx = {idx(p): levels[p] for p in sorted_prices}
    price_by_idx = {idx(p): p for p in sorted_prices}
    indices = sorted(by_idx.keys())

    best_buy = cur_buy = 0
    best_sell = cur_sell = 0
    buy_levels: list[float] = []
    sell_levels: list[float] = []
    prev_idx: int | None = None
    for i in indices:
        bid, ask = by_idx[i]
        below = by_idx.get(i - 1)  # one tick below
        above = by_idx.get(i + 1)  # one tick above
        buy_imb = below is not None and below[1] > 0 and bid >= ratio * below[1]
        # also count strong bid vs near-zero ask below
        if below is not None and below[1] == 0 and bid > 0:
            buy_imb = True
        sell_imb = above is not None and above[0] > 0 and ask >= ratio * above[0]
        if above is not None and above[0] == 0 and ask > 0:
            sell_imb = True

        if buy_imb:
            buy_levels.append(price_by_idx[i])
        if sell_imb:
            sell_levels.append(price_by_idx[i])

        contiguous = prev_idx is not None and i == prev_idx + 1
        cur_buy = (cur_buy + 1) if (buy_imb and contiguous) else (1 if buy_imb else 0)
        cur_sell = (cur_sell + 1) if (sell_imb and contiguous) else (1 if sell_imb else 0)
        best_buy = max(best_buy, cur_buy)
        best_sell = max(best_sell, cur_sell)
        prev_idx = i
    return _StackResult(best_buy, best_sell, buy_levels, sell_levels)


def _flow_bias(
    buy_stacked: bool, sell_stacked: bool, delta: float, delta_min: float
) -> int:
    """Directional bias of one timeframe's order flow: +1 long, -1 short, 0."""
    delta_pos = delta > delta_min
    delta_neg = delta < -delta_min
    if buy_stacked and delta_pos:
        return 1
    if sell_stacked and delta_neg:
        return -1
    if buy_stacked and not sell_stacked and not delta_neg:
        return 1
    if sell_stacked and not buy_stacked and not delta_pos:
        return -1
    if delta_pos and not sell_stacked:
        return 1
    if delta_neg and not buy_stacked:
        return -1
    return 0


_TF_WEIGHTS = (0.3, 0.2)  # confirm intervals, in order; fast window holds 0.5


def _blend_bias(fast: int, confirms: list[int | None]) -> tuple[str, float, float]:
    """Weighted multi-TF blend -> (direction, confidence, score).

    Missing confirm data (None) contributes nothing and its weight is dropped
    so a sparse higher TF can't dilute the signal artificially.
    """
    score = 0.5 * fast
    weight_used = 0.5
    for bias, w in zip(confirms, _TF_WEIGHTS):
        if bias is not None:
            score += w * bias
            weight_used += w
    norm = score / weight_used if weight_used > 0 else 0.0
    if norm >= 0.35:
        direction = "long"
    elif norm <= -0.35:
        direction = "short"
    else:
        direction = "neutral"
    confidence = round(min(0.9, 0.3 + 0.6 * abs(norm)), 3)
    return direction, confidence, round(norm, 3)


class OrderflowSource:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        db: str,
        password: str | None,
        symbol: str,
        staleness_seconds: float,
        timeout: float,
        interval: str,
        lookback_candles: int,
        tick_size: float,
        imbalance_ratio: float,
        stacked_levels: int,
        delta_min_abs: float,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.db = db
        self.password = password
        self.symbol = symbol
        self.staleness_seconds = staleness_seconds
        self.timeout = timeout
        self.interval = interval
        self.lookback = lookback_candles
        self.tick = tick_size
        self.ratio = imbalance_ratio
        self.stacked = stacked_levels
        self.delta_min_abs = delta_min_abs
        # Higher timeframes whose latest closed candle confirms/contradicts the
        # fast window. The vote is a weighted blend (fast 0.5, then these in
        # order at 0.3 / 0.2) so a noisy 1m burst can't flip the voice alone.
        self.confirm_intervals: tuple[str, ...] = ("15m", "1h")
        self.name = "orderflow"

    def _conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} user={self.user} "
            f"dbname={self.db} password={self.password or ''} "
            f"connect_timeout={int(max(1, self.timeout))}"
        )

    def poll(self) -> Vote:
        if self.password is None:
            return offline(self.name, "no DB password (orderflow .env missing or unreadable)")
        try:
            with psycopg.connect(self._conninfo()) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        '''
                        SELECT "openTime", "volumeDelta", "priceLevels",
                               "close", "high", "low", "volume"
                        FROM footprint_candle
                        WHERE symbol = %s AND interval = %s
                        ORDER BY "openTime" DESC
                        LIMIT %s
                        ''',
                        (self.symbol, self.interval, self.lookback),
                    )
                    rows = cur.fetchall()
                    tf_rows: dict[str, tuple | None] = {}
                    for tf in self.confirm_intervals:
                        cur.execute(
                            '''
                            SELECT "volumeDelta", "priceLevels", "openTime"
                            FROM footprint_candle
                            WHERE symbol = %s AND interval = %s
                            ORDER BY "openTime" DESC
                            LIMIT 1
                            ''',
                            (self.symbol, tf),
                        )
                        tf_rows[tf] = cur.fetchone()
        except psycopg.OperationalError as exc:
            return offline(self.name, f"db unreachable: {str(exc).splitlines()[0]}")
        except psycopg.errors.UndefinedTable:
            return offline(self.name, "footprint_candle table not created yet")
        except psycopg.Error as exc:
            return offline(self.name, f"db error: {str(exc).splitlines()[0]}")

        if not rows:
            return offline(self.name, "no footprint rows (websocket geo-blocked / no data)")

        newest_open = rows[0][0]
        age = None
        if isinstance(newest_open, datetime):
            if newest_open.tzinfo is None:
                newest_open = newest_open.replace(tzinfo=timezone.utc)
            age = max(0.0, (datetime.now(timezone.utc) - newest_open).total_seconds())

        # Newest candle drives the stacked-imbalance read; delta is summed.
        newest_levels = _coerce_levels(rows[0][2])
        stack = _max_consecutive_imbalance(newest_levels, self.tick, self.ratio)

        def _f(value: object) -> float | None:
            try:
                return float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        total_delta = 0.0
        total_volume = 0.0
        per_candle_delta: list[float] = []
        for row in rows:
            d = _f(row[1]) or 0.0
            total_delta += d
            per_candle_delta.append(round(d, 4))
            v = _f(row[6])
            if v is not None:
                total_volume += v

        # Newest candle OHLC + lookback-window high/low.
        close_price = _f(rows[0][3])
        highs = [h for h in (_f(r[4]) for r in rows) if h is not None]
        lows = [low for low in (_f(r[5]) for r in rows) if low is not None]
        window_high = max(highs) if highs else None
        window_low = min(lows) if lows else None

        buy_stacked = stack.buy_stack >= self.stacked
        sell_stacked = stack.sell_stack >= self.stacked
        fast_bias = _flow_bias(buy_stacked, sell_stacked, total_delta, self.delta_min_abs)

        # Higher-TF confirmations from each interval's latest closed candle.
        tf_bias: dict[str, int | None] = {}
        for tf in self.confirm_intervals:
            row = tf_rows.get(tf)
            if row is None or _tf_is_stale(row[2], tf):
                # Missing OR stale higher-TF candle -> None drops its blend
                # weight rather than feeding outdated order flow into the vote.
                tf_bias[tf] = None
                continue
            tf_delta = _f(row[0]) or 0.0
            tf_stack = _max_consecutive_imbalance(_coerce_levels(row[1]), self.tick, self.ratio)
            tf_bias[tf] = _flow_bias(
                tf_stack.buy_stack >= self.stacked,
                tf_stack.sell_stack >= self.stacked,
                tf_delta,
                self.delta_min_abs,
            )

        direction, conf, blend_score = _blend_bias(
            fast_bias, [tf_bias.get(tf) for tf in self.confirm_intervals]
        )

        bias_str = " ".join(
            f"{tf}:{'?' if b is None else ('+' if b > 0 else '-' if b < 0 else '0')}"
            for tf, b in tf_bias.items()
        )
        detail = (
            f"buy_stack={stack.buy_stack} sell_stack={stack.sell_stack} "
            f"delta(sum {len(rows)}c)={total_delta:.2f} | "
            f"fast:{'+' if fast_bias > 0 else '-' if fast_bias < 0 else '0'} {bias_str} "
            f"blend={blend_score:+.2f}"
        )
        # per_candle_delta is newest-first (matches row order); reverse to
        # chronological so the dashboard reads left=oldest -> right=newest.
        return Vote(
            source=self.name,
            direction=direction,  # type: ignore[arg-type]
            confidence=conf,
            age_seconds=age,
            detail=detail,
            extra={
                "buy_stack": stack.buy_stack,
                "sell_stack": stack.sell_stack,
                "buy_stack_levels": sorted(stack.buy_levels),
                "sell_stack_levels": sorted(stack.sell_levels),
                "buy_stack_count": len(stack.buy_levels),
                "sell_stack_count": len(stack.sell_levels),
                "total_delta": round(total_delta, 4),
                "per_candle_delta": list(reversed(per_candle_delta)),
                "total_volume": round(total_volume, 4),
                "close": close_price,
                "window_high": window_high,
                "window_low": window_low,
                "candles": len(rows),
                "interval": self.interval,
                "tf_bias": tf_bias,
                "fast_bias": fast_bias,
                "blend_score": blend_score,
                "confirm_intervals": list(self.confirm_intervals),
                "tick_size": self.tick,
                "imbalance_ratio": self.ratio,
                "stacked_threshold": self.stacked,
            },
        )
