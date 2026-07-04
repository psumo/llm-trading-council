"""Source 1: LLM_trader (Gemini Pro voice).

Reads the append-only SQLite trade_history table. The DB is WAL-mode and may
not exist until the bot's first decision -- both cases degrade to offline.

Action -> direction mapping:
  BUY  / LONG / OPEN_LONG          -> long
  SELL / SHORT / OPEN_SHORT        -> short
  CLOSE_LONG / CLOSE_SHORT / CLOSE -> neutral (exit; noted in detail)
  anything else                    -> neutral

last_analysis.json is read only for liveness/age. previous_response.json holds
the latest full LLM response; its text_analysis embeds a JSON blob with
analysis.signal (BUY/SELL/HOLD) + analysis.confidence -- that is the live
stance between trades (HOLD never reaches the trades DB), so when it is fresher
than the latest trade row it becomes the vote.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .base import Vote, offline

_LONG = {"BUY", "LONG", "OPEN_LONG", "ENTER_LONG"}
_SHORT = {"SELL", "SHORT", "OPEN_SHORT", "ENTER_SHORT"}
_EXIT = {"CLOSE", "CLOSE_LONG", "CLOSE_SHORT", "EXIT", "EXIT_LONG", "EXIT_SHORT"}

# Curated indicator subset surfaced to the dashboard / judge (the full response
# carries 80+; these are the decision-relevant ones).
_CURATED_INDICATORS = (
    "rsi",
    "macd_hist",
    "macd_line",
    "macd_signal",
    "atr",
    "atr_percent",
    "vwap",
    "supertrend",
    "supertrend_direction",
    "adx",
    "plus_di",
    "minus_di",
    "choppiness",
    "bb_percent_b",
    "bb_upper",
    "bb_lower",
    "basic_support",
    "basic_resistance",
    "pivot_point",
    "sma_50",
    "sma_200",
)


def _num(value: object) -> float | None:
    try:
        return round(float(value), 6)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _curated_indicators(response: dict) -> dict[str, float | None]:
    return {k: _num(response.get(k)) for k in _CURATED_INDICATORS if k in response}


def _symbol_variants(symbol: str) -> list[str]:
    """Exchange form (SPCXUSDT) vs ccxt unified forms (SPCX/USDT, SPCX/USDT:USDT)."""
    variants = {symbol}
    compact = symbol.replace("/", "").replace(":", "")
    variants.add(compact)
    for quote in ("USDT", "USDC", "USD", "BTC"):
        if compact.endswith(quote) and len(compact) > len(quote):
            base = compact[: -len(quote)]
            variants.add(f"{base}/{quote}")
            variants.add(f"{base}/{quote}:{quote}")
    return sorted(variants)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Try a couple of common fallbacks.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _confidence_to_float(raw: object) -> float:
    """confidence column is TEXT; accept 'high'/'medium'/'low' or a number."""
    if raw is None:
        return 0.5
    s = str(raw).strip().lower()
    mapping = {"high": 0.85, "medium": 0.6, "med": 0.6, "low": 0.35, "very high": 0.95}
    if s in mapping:
        return mapping[s]
    try:
        v = float(s.rstrip("%"))
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))
    except ValueError:
        return 0.5


def _extract_analysis_json(text: str) -> dict | None:
    """Extract the first valid JSON object containing an "analysis" key.

    The previous greedy ``re.search(r"\\{.*\\}", DOTALL)`` spanned from the very
    first '{' to the very LAST '}' in the text, so any surrounding prose with
    multiple braces (e.g. "{note} ... {actual json} ... {trailer}") produced an
    unparseable blob. Instead we scan from each '{' and use
    ``json.JSONDecoder().raw_decode`` to parse exactly one object at that
    position; the first one that parses AND carries an "analysis" key wins.
    Returns None when no such object is found.
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "analysis" in obj:
            return obj
        idx = text.find("{", idx + 1)
    return None


class LlmTraderSource:
    def __init__(self, db_path: str, last_analysis_path: str, symbol: str, staleness_seconds: float):
        self.db_path = Path(db_path)
        self.last_analysis_path = Path(last_analysis_path)
        self.symbol = symbol
        self.staleness_seconds = staleness_seconds
        self.name = "llm_trader"
        self._last_seen_id = 0

    def _read_latest_row(self) -> sqlite3.Row | None:
        # Open read-only via URI so we never create the DB or block the writer.
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            conn.row_factory = sqlite3.Row
            variants = _symbol_variants(self.symbol)
            placeholders = ",".join("?" for _ in variants)
            cur = conn.execute(
                "SELECT id, timestamp, symbol, action, confidence, price, reasoning, created_at "
                f"FROM trade_history WHERE symbol IN ({placeholders}) ORDER BY id DESC LIMIT 1",
                variants,
            )
            return cur.fetchone()
        finally:
            conn.close()

    def _read_analysis_stance(
        self,
    ) -> tuple[str, float, float, str, dict, dict] | None:
        """(signal, confidence 0-1, age_seconds, snippet, analysis, indicators).

        `analysis` is the full embedded analysis blob (signal/levels/trend/
        reasoning/entry/SL/TP/RR...); `indicators` is the curated subset from
        the response top level. Returns None when no usable stance is found.
        """
        path = self.last_analysis_path.parent / "previous_response.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        ts = _parse_ts(data.get("timestamp"))
        if ts is None:
            return None
        age = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
        response = data.get("response") if isinstance(data.get("response"), dict) else {}
        text = str(response.get("text_analysis") or "")
        blob = _extract_analysis_json(text)
        if blob is None:
            return None
        analysis = blob.get("analysis") if isinstance(blob, dict) else None
        if not isinstance(analysis, dict):
            return None
        signal = str(analysis.get("signal") or "").strip().upper()
        if not signal:
            return None
        confidence = _confidence_to_float(analysis.get("confidence"))
        summary = str(
            analysis.get("summary") or analysis.get("reasoning") or ""
        ).replace("\n", " ").strip()
        if not summary:
            trend = analysis.get("trend")
            if isinstance(trend, dict):
                summary = f"trend {trend.get('direction', '?')}"
        indicators = _curated_indicators(response)
        return signal, confidence, age, summary[:160], analysis, indicators

    def _analysis_age(self) -> float | None:
        if not self.last_analysis_path.is_file():
            return None
        try:
            data = json.loads(self.last_analysis_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        dt = _parse_ts(data.get("timestamp"))
        if dt is None:
            return None
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())

    def _stance_vote(self) -> Vote | None:
        stance = self._read_analysis_stance()
        if stance is None:
            return None
        signal, confidence, age, snippet, analysis, indicators = stance
        if signal in _LONG:
            direction = "long"
        elif signal in _SHORT:
            direction = "short"
        else:
            direction = "neutral"
        extra = self._build_analysis_extra(signal, analysis, indicators)
        return Vote(
            source=self.name,
            direction=direction,  # type: ignore[arg-type]
            confidence=confidence,
            age_seconds=age,
            detail=f"{signal} (analysis): {snippet}".rstrip(": "),
            extra=extra,
        )

    @staticmethod
    def _build_analysis_extra(
        signal: str, analysis: dict, indicators: dict
    ) -> dict:
        """Full trade context from the analysis blob + curated indicators."""
        reasoning = str(analysis.get("reasoning") or analysis.get("summary") or "")
        return {
            "action": signal,
            "from": "previous_response.json",
            "signal": analysis.get("signal"),
            "confidence": analysis.get("confidence"),
            "reasoning": reasoning.strip(),
            "entry": _num(analysis.get("entry_price") or analysis.get("entry")),
            "stop_loss": _num(analysis.get("stop_loss")),
            "take_profit": _num(analysis.get("take_profit")),
            "risk_reward": _num(analysis.get("risk_reward_ratio")),
            "position_size": _num(analysis.get("position_size")),
            "key_levels": analysis.get("key_levels"),
            "trend": analysis.get("trend"),
            "confluence_factors": analysis.get("confluence_factors"),
            "indicators": indicators,
        }

    def poll(self) -> Vote:
        if not self.db_path.is_file():
            vote = self._stance_vote()
            if vote is not None:
                return vote
            note = "trade_history.db not created yet"
            analysis_age = self._analysis_age()
            if analysis_age is not None:
                note = f"bot alive (last analysis {int(analysis_age)}s ago) but no trades recorded yet"
            return offline(self.name, note)
        try:
            row = self._read_latest_row()
        except sqlite3.OperationalError as exc:
            # Table missing or DB locked beyond timeout.
            return offline(self.name, f"sqlite unavailable: {exc}")
        except sqlite3.Error as exc:
            return offline(self.name, f"sqlite error: {exc}")

        if row is None:
            vote = self._stance_vote()
            if vote is not None:
                return vote
            return offline(self.name, "no trades for symbol yet")
        # Prefer the analysis stance when it is fresher than the trade row
        # (HOLD decisions never reach the trades DB).
        stance_vote = self._stance_vote()
        row_ts = _parse_ts(row["timestamp"]) or _parse_ts(row["created_at"])
        if stance_vote is not None and row_ts is not None and stance_vote.age_seconds is not None:
            row_age = max(0.0, (datetime.now(timezone.utc) - row_ts).total_seconds())
            if stance_vote.age_seconds < row_age:
                return stance_vote

        self._last_seen_id = max(self._last_seen_id, int(row["id"]))
        action = (row["action"] or "").strip().upper()
        if action in _LONG:
            direction = "long"
        elif action in _SHORT:
            direction = "short"
        elif action in _EXIT:
            direction = "neutral"
        else:
            direction = "neutral"

        ts = _parse_ts(row["timestamp"]) or _parse_ts(row["created_at"])
        age = None
        if ts is not None:
            age = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
        # Prefer the fresher of trade-age and analysis-age for liveness.
        analysis_age = self._analysis_age()
        liveness_age: float | None = age
        if analysis_age is not None and (age is None or analysis_age < age):
            # Bot is actively analysing even if last *trade* is old.
            liveness_age = analysis_age

        reasoning = (row["reasoning"] or "").strip().replace("\n", " ")
        snippet = reasoning[:160] + ("..." if len(reasoning) > 160 else "")
        exit_note = " [exit]" if action in _EXIT else ""
        detail = f"{action}{exit_note} @ {row['price']}: {snippet}".strip()

        # Start from the analysis blob (richest context) and overlay the actual
        # executed-trade fields from the DB row.
        extra: dict = {}
        if stance_vote is not None:
            extra = dict(stance_vote.extra)
        extra.update(
            {
                "action": action,
                "from": "trade_history",
                "trade_id": int(row["id"]),
                "trade_price": _num(row["price"]),
                "trade_stop_loss": _num(self._row_value(row, "stop_loss")),
                "trade_take_profit": _num(self._row_value(row, "take_profit")),
                "trade_reasoning": (row["reasoning"] or "").strip(),
                "is_exit": action in _EXIT,
            }
        )
        return Vote(
            source=self.name,
            direction=direction,  # type: ignore[arg-type]
            confidence=_confidence_to_float(row["confidence"]),
            age_seconds=liveness_age,
            detail=detail,
            extra=extra,
        )

    @staticmethod
    def _row_value(row: sqlite3.Row, key: str) -> object:
        """Safe column access -- the row may predate a column being added."""
        try:
            return row[key]
        except (IndexError, KeyError):
            return None
