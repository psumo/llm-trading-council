"""Live mark/last price source for the tracker.

Primary: Binance USD-M futures REST ticker (verified reachable on this network).
Fallback: the latest footprint_candle close already present in the orderflow
vote's extra payload (no extra DB round-trip needed).

A fetch failure NEVER raises out of get_price -- it returns a PriceResult whose
status carries the reason so the polling loop can skip the tick and surface the
detail in /api/state.tracker.price_status.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_BINANCE_URL = "https://fapi.binance.com/fapi/v1/ticker/price"


@dataclass(frozen=True)
class PriceResult:
    """Outcome of a price fetch. price is None on failure.

    stale=True means a price WAS returned but it has not changed for longer
    than the staleness window -- typical for restricted-hours instruments
    (e.g. TradFi perps like SPCX) outside their session, where the ticker
    keeps reporting the last frozen trade. Stale prices must not drive
    SL/TP/timeout evaluation or new entries.
    """

    price: float | None
    source: str  # "binance" | "orderflow" | "none"
    status: str  # "ok" | descriptive error / fallback reason
    stale: bool = False


class PriceFetcher:
    """Fetches one symbol's price from Binance futures with an orderflow fallback."""

    def __init__(
        self,
        symbol: str,
        timeout: float = 5.0,
        enabled: bool = True,
        stale_after_seconds: float = 300.0,
    ):
        self.symbol = symbol
        self.timeout = timeout
        self.enabled = enabled
        self.stale_after_seconds = stale_after_seconds
        self._last_price: float | None = None
        self._last_change_ts: float = 0.0

    def _apply_staleness(self, result: PriceResult) -> PriceResult:
        """Flag the result stale when the price has been frozen too long."""
        import time

        if result.price is None:
            return result
        now = time.time()
        if self._last_price is None or result.price != self._last_price:
            self._last_price = result.price
            self._last_change_ts = now
            return result
        frozen_for = now - self._last_change_ts
        if frozen_for >= self.stale_after_seconds:
            return PriceResult(
                result.price,
                result.source,
                f"stale: unchanged for {int(frozen_for)}s (market closed?)",
                stale=True,
            )
        return result

    def _from_binance(self) -> PriceResult | None:
        """Return a successful PriceResult, or None to trigger the fallback."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(_BINANCE_URL, params={"symbol": self.symbol})
            if resp.status_code >= 400:
                return PriceResult(
                    None, "none", f"binance HTTP {resp.status_code}"
                )
            data = resp.json()
            raw = data.get("price")
            price = float(raw)
            if price <= 0:
                return PriceResult(None, "none", "binance returned non-positive price")
            return PriceResult(price, "binance", "ok")
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            # Signal the caller to try the fallback; carry the reason.
            return PriceResult(None, "none", f"binance error: {type(exc).__name__}: {exc}")

    def get_price(self, fallback_close: float | None) -> PriceResult:
        """Best-effort current price.

        When REST polling is disabled, or Binance fails, fall back to the
        orderflow footprint close if one is available.
        """
        if self.enabled:
            result = self._from_binance()
            if result is not None and result.price is not None:
                return self._apply_staleness(result)
            reason = result.status if result is not None else "binance unavailable"
        else:
            reason = "binance polling disabled (config tracker.price_poll=false)"

        if fallback_close is not None and fallback_close > 0:
            return self._apply_staleness(
                PriceResult(
                    float(fallback_close),
                    "orderflow",
                    f"fallback to orderflow close ({reason})",
                )
            )
        return PriceResult(None, "none", f"no price available ({reason})")
