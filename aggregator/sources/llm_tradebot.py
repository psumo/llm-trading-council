"""Source 2: LLM-TradeBot (Gemini Flash voice), HTTP JSON API.

Logs in (cookie session) then polls GET /api/status. Maps the latest decision
for the configured symbol to long/short/neutral. The bot is only running while
its dashboard is up; any connection error degrades to offline.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .base import Vote, offline

_LONG = {"BUY", "LONG", "OPEN_LONG", "ENTER_LONG", "STRONG_BUY"}
_SHORT = {"SELL", "SHORT", "OPEN_SHORT", "ENTER_SHORT", "STRONG_SELL"}
_NEUTRAL = {"HOLD", "WAIT", "NEUTRAL", "FLAT", "CLOSE", "NONE", ""}


def _parse_ts(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # epoch seconds or ms
        secs = float(value)
        if secs > 1e12:
            secs /= 1000.0
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _map_action(action: str) -> str:
    a = action.strip().upper()
    if a in _LONG:
        return "long"
    if a in _SHORT:
        return "short"
    return "neutral"


def _extract_confidence(decision: dict) -> float:
    for key in ("confidence", "critic_confidence", "score"):
        if key in decision and decision[key] is not None:
            try:
                v = float(decision[key])
                if v > 1.0:
                    v /= 100.0
                return max(0.0, min(1.0, v))
            except (TypeError, ValueError):
                continue
    return 0.5


class LlmTradebotSource:
    def __init__(self, base_url: str, password: str, symbol: str, staleness_seconds: float, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.symbol = symbol
        self.staleness_seconds = staleness_seconds
        self.timeout = timeout
        self.name = "llm_tradebot"

    def _login(self, client: httpx.Client) -> bool:
        # Only the password POST sets the session cookie; /api/login/default
        # merely *discloses* the default password (returns 200 with no cookie),
        # so it is used solely as a password-discovery fallback.
        # ConnectError is allowed to propagate so the caller can distinguish a
        # bot that is *down* from one that is up but rejecting auth.
        try:
            r = client.post(f"{self.base_url}/api/login", json={"password": self.password})
            if r.status_code < 400:
                return True
        except httpx.ConnectError:
            raise
        except httpx.HTTPError:
            return False
        try:
            r = client.get(f"{self.base_url}/api/login/default")
            if r.status_code < 400:
                default_pw = r.json().get("password")
                if default_pw and default_pw != self.password:
                    r = client.post(f"{self.base_url}/api/login", json={"password": default_pw})
                    return r.status_code < 400
            return False
        except httpx.ConnectError:
            raise
        except (httpx.HTTPError, ValueError):
            return False

    def _decision_for_symbol(self, status: dict) -> dict | None:
        decision = status.get("decision")
        # decision may be a dict keyed by symbol, or a single decision object.
        if isinstance(decision, dict):
            if self.symbol in decision and isinstance(decision[self.symbol], dict):
                return decision[self.symbol]
            # single object that already names the symbol (or no symbol key)
            sym = decision.get("symbol")
            if sym is None or sym == self.symbol:
                return decision
        # Fall back to scanning decision_history for the symbol.
        history = status.get("decision_history")
        if isinstance(history, list):
            for item in reversed(history):
                if isinstance(item, dict) and item.get("symbol") in (None, self.symbol):
                    return item
        return None

    def poll(self) -> Vote:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                if not self._login(client):
                    return offline(self.name, "login failed (bot up but auth rejected)")
                resp = client.get(f"{self.base_url}/api/status")
                if resp.status_code >= 400:
                    return offline(self.name, f"/api/status HTTP {resp.status_code}")
                status = resp.json()
        except httpx.ConnectError:
            return offline(self.name, "bot not running (connection refused)")
        except httpx.HTTPError as exc:
            return offline(self.name, f"http error: {exc}")
        except ValueError:
            return offline(self.name, "invalid JSON from /api/status")

        if not isinstance(status, dict):
            return offline(self.name, "unexpected /api/status payload")

        decision = self._decision_for_symbol(status)
        if not decision:
            return offline(self.name, "no decision for symbol yet")

        action = str(decision.get("action") or decision.get("decision") or decision.get("signal") or "")
        direction = _map_action(action)
        ts = _parse_ts(decision.get("timestamp") or decision.get("time") or decision.get("ts"))
        age = None
        if ts is not None:
            age = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())

        reason = str(decision.get("reasoning") or decision.get("reason") or decision.get("rationale") or "")
        reason = reason.replace("\n", " ").strip()
        snippet = reason[:160] + ("..." if len(reason) > 160 else "")

        market_raw = status.get("market")
        market: dict = market_raw if isinstance(market_raw, dict) else {}
        regime = self._market_regime(market)
        detail = f"{action or 'decision'} ({regime}): {snippet}".strip().rstrip(":").strip()

        extra = self._build_extra(decision, market, status)
        return Vote(
            source=self.name,
            direction=direction,  # type: ignore[arg-type]
            confidence=_extract_confidence(decision),
            age_seconds=age,
            detail=detail or action or "decision",
            extra=extra,
        )

    def _market_regime(self, market: dict) -> str:
        regime = market.get("regime")
        return str(regime) if regime is not None else ""

    def _market_price(self, market: dict) -> float | None:
        """market.price is either a scalar or a dict keyed by symbol."""
        price = market.get("price")
        if isinstance(price, dict):
            price = price.get(self.symbol)
        try:
            return float(price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _build_extra(self, decision: dict, market: dict, status: dict) -> dict:
        """Capture the bot's full trade context for the dashboard / judge."""
        vote_details = decision.get("vote_details")
        order_params = (
            decision.get("order_params")
            or decision.get("trade_params")
            or decision.get("trade_params_dict")
        )
        reason = str(
            decision.get("reasoning") or decision.get("reason") or decision.get("rationale") or ""
        ).strip()

        va_raw = status.get("virtual_account")
        va: dict = va_raw if isinstance(va_raw, dict) else {}
        virtual_account = {
            "balance": va.get("current_balance", va.get("balance")),
            "available_balance": va.get("available_balance"),
            "initial_balance": va.get("initial_balance"),
            "positions": va.get("positions"),
            "total_unrealized_pnl": va.get("total_unrealized_pnl"),
            "cumulative_realized_pnl": va.get("cumulative_realized_pnl"),
        }

        return {
            "action": decision.get("action") or decision.get("decision") or decision.get("signal"),
            "confidence": decision.get("confidence"),
            "weighted_score": decision.get("weighted_score"),
            "reasoning": reason,
            "regime": self._market_regime(market),
            "risk_level": decision.get("risk_level"),
            "vote_details": vote_details if isinstance(vote_details, dict) else None,
            "order_params": order_params if isinstance(order_params, dict) else None,
            "market_price": self._market_price(market),
            "market_position": market.get("position"),
            "virtual_account": virtual_account,
        }
