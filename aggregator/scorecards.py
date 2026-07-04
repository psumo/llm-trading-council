"""Per-voice scorecards: score each source independently vs price outcomes.

Unlike the position tracker (which only scores trades the judge actually
opened), the scorecard scores every source continuously:

  * Each poll tick, for every source, if its direction CHANGED versus that
    source's previous recorded row, append a row to `voice_signals`
    (ts, source, direction, confidence, price, regime, resolved, outcome,
    move_pct). Recording only on change keeps the table small.
  * A resolver runs each tick: any unresolved row whose age >= the horizon is
    resolved by comparing the CURRENT live price to the recorded price.
      long  correct  when move_pct >= +min_move_pct
      short correct  when move_pct <= -min_move_pct
      |move_pct| < min_move_pct -> "flat" (excluded from hit rate)
  * Rolling stats over the last `window` resolved signals per source: hit rate,
    avg favourable/adverse move, current streak, plus a per-regime breakdown.

All SQL is parameterized; failures are surfaced via the returned status string
and never raise out of the polling loop.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import ScorecardsCfg

_SOURCES = ("llm_trader", "llm_tradebot", "orderflow")
# Directions worth scoring (offline/neutral carry no directional claim).
_SCORABLE = {"long", "short"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS voice_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL DEFAULT 'BTCUSDT',
    source      TEXT NOT NULL,
    direction   TEXT NOT NULL,
    confidence  REAL,
    price       REAL NOT NULL,
    regime      TEXT,
    resolved    INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT,
    resolve_price REAL,
    move_pct    REAL,
    outcome     TEXT
);
CREATE INDEX IF NOT EXISTS idx_vs_source ON voice_signals(source, id);
CREATE INDEX IF NOT EXISTS idx_vs_unresolved ON voice_signals(resolved);
"""

# The symbol index is created AFTER the column-add migration so an existing
# pre-multipair table (no `symbol` column yet) does not error on CREATE INDEX.
_SYMBOL_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_vs_symbol "
    "ON voice_signals(symbol, source, id)"
)

_INSERT_SQL = (
    "INSERT INTO voice_signals (ts, symbol, source, direction, confidence, price, regime, resolved) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
)
# Per-symbol "last recorded direction for this source" (record only on change).
_LAST_DIR_SQL = (
    "SELECT direction FROM voice_signals WHERE symbol = ? AND source = ? "
    "ORDER BY id DESC LIMIT 1"
)
# The resolver is per-symbol: each symbol resolves its own unresolved rows
# against that symbol's live price.
_UNRESOLVED_SQL = (
    "SELECT id, ts, source, direction, price FROM voice_signals "
    "WHERE resolved = 0 AND symbol = ?"
)
_RESOLVE_SQL = (
    "UPDATE voice_signals SET resolved = 1, resolved_at = ?, resolve_price = ?, "
    "move_pct = ?, outcome = ? WHERE id = ?"
)
_RESOLVED_FOR_SOURCE_SQL = (
    "SELECT direction, regime, move_pct, outcome FROM voice_signals "
    "WHERE symbol = ? AND source = ? AND resolved = 1 ORDER BY id DESC LIMIT ?"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def classify_outcome(
    direction: str, move_pct: float, min_move_pct: float
) -> str:
    """Resolve a directional signal against the realized % price move.

    move_pct is the signed price change (resolve - recorded) / recorded * 100.
    A long is "correct" when price rose at least min_move_pct; a short when it
    fell at least min_move_pct; otherwise "flat" (excluded from hit rate).
    """
    if abs(move_pct) < min_move_pct:
        return "flat"
    if direction == "long":
        return "correct" if move_pct > 0 else "wrong"
    if direction == "short":
        return "correct" if move_pct < 0 else "wrong"
    return "flat"


def _stats_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute hit rate / avg moves / streak from newest-first resolved rows."""
    decided = [r for r in rows if r["outcome"] in ("correct", "wrong")]
    correct = sum(1 for r in decided if r["outcome"] == "correct")
    n = len(decided)
    right_moves = [abs(r["move_pct"]) for r in decided if r["outcome"] == "correct"]
    wrong_moves = [abs(r["move_pct"]) for r in decided if r["outcome"] == "wrong"]
    # Current streak: walk newest-first while outcome is constant.
    streak = 0
    streak_kind = ""
    for r in decided:
        if not streak_kind:
            streak_kind = r["outcome"]
            streak = 1
        elif r["outcome"] == streak_kind:
            streak += 1
        else:
            break
    return {
        "resolved": n,
        "correct": correct,
        "hit_rate": round(correct / n * 100.0, 1) if n else None,
        "avg_move_right": round(sum(right_moves) / len(right_moves), 4)
        if right_moves
        else None,
        "avg_move_wrong": round(sum(wrong_moves) / len(wrong_moves), 4)
        if wrong_moves
        else None,
        "streak": streak,
        "streak_kind": streak_kind,
    }


def _regime_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    regimes = {r["regime"] or "unknown" for r in rows}
    for regime in sorted(regimes):
        subset = [r for r in rows if (r["regime"] or "unknown") == regime]
        decided = [r for r in subset if r["outcome"] in ("correct", "wrong")]
        correct = sum(1 for r in decided if r["outcome"] == "correct")
        n = len(decided)
        out[regime] = {
            "resolved": n,
            "hit_rate": round(correct / n * 100.0, 1) if n else None,
        }
    return out


class Scorecards:
    """Per-symbol view over the shared voice_signals table.

    Each instrument constructs one Scorecards scoped to its `symbol`; all
    instances share the same SQLite file but record/resolve/report only their
    own symbol's rows (the `symbol` column scopes every query).
    """

    def __init__(self, cfg: ScorecardsCfg, db_path: str, symbol: str = "BTCUSDT"):
        self.cfg = cfg
        self.symbol = symbol
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Each per-symbol Scorecards opens its OWN connection to the shared DB
        # file, and runs in parallel worker threads. A reentrant lock serializes
        # this connection's use; busy_timeout makes cross-connection write
        # contention (with the TrackerStore connection) wait rather than error.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()
        self.last_status: str = "starting"
        self.last_recorded: int = 0
        self.last_resolved: int = 0

    def _migrate(self) -> None:
        """Idempotently add the `symbol` column to a pre-multipair table and
        backfill existing rows to 'BTCUSDT' (the only symbol that existed)."""
        cur = self._conn.execute("PRAGMA table_info(voice_signals)")
        cols = {row["name"] for row in cur.fetchall()}
        if "symbol" not in cols:
            self._conn.execute(
                "ALTER TABLE voice_signals ADD COLUMN symbol TEXT NOT NULL "
                "DEFAULT 'BTCUSDT'"
            )
        self._conn.execute(
            "UPDATE voice_signals SET symbol = 'BTCUSDT' "
            "WHERE symbol IS NULL OR symbol = ''"
        )
        self._conn.execute(_SYMBOL_INDEX_SQL)

    # ---- recording -----------------------------------------------------

    def _last_direction(self, source: str) -> str | None:
        with self._lock:
            cur = self._conn.execute(_LAST_DIR_SQL, (self.symbol, source))
            row = cur.fetchone()
        return row["direction"] if row else None

    def record(
        self,
        directions: dict[str, str],
        confidences: dict[str, float],
        price: float,
        regime: str,
    ) -> int:
        """Insert a row per source whose direction changed (and is scorable).

        Returns the number of rows written. Only `long`/`short` are recorded;
        a transition to neutral/offline is ignored (no directional claim) but
        still updates what counts as "previous" via the latest scorable row.
        """
        written = 0
        ts = _now_iso()
        with self._lock:
            for source in _SOURCES:
                direction = str(directions.get(source, "offline")).lower()
                if direction not in _SCORABLE:
                    continue
                prev = self._last_direction(source)
                if prev == direction:
                    continue
                conf = float(confidences.get(source, 0.0) or 0.0)
                self._conn.execute(
                    _INSERT_SQL,
                    (ts, self.symbol, source, direction, conf, float(price), regime),
                )
                written += 1
            if written:
                self._conn.commit()
        self.last_recorded = written
        return written

    # ---- resolving -----------------------------------------------------

    def resolve(self, price: float) -> int:
        """Resolve any unresolved rows older than the horizon against `price`.

        Returns the number of rows resolved this call.
        """
        horizon = self.cfg.horizon_minutes * 60.0
        now = _now()
        resolved = 0
        with self._lock:
            cur = self._conn.execute(_UNRESOLVED_SQL, (self.symbol,))
            pending = cur.fetchall()
            for row in pending:
                ts = _parse_ts(row["ts"])
                if ts is None:
                    continue
                if (now - ts).total_seconds() < horizon:
                    continue
                recorded_price = row["price"]
                if not recorded_price or recorded_price <= 0:
                    # Cannot compute a move; mark flat/resolved to avoid replay.
                    self._conn.execute(
                        _RESOLVE_SQL,
                        (now.isoformat(), float(price), 0.0, "flat", row["id"]),
                    )
                    resolved += 1
                    continue
                move_pct = (price - recorded_price) / recorded_price * 100.0
                outcome = classify_outcome(
                    row["direction"], move_pct, self.cfg.min_move_pct
                )
                self._conn.execute(
                    _RESOLVE_SQL,
                    (now.isoformat(), float(price), round(move_pct, 6), outcome, row["id"]),
                )
                resolved += 1
            if resolved:
                self._conn.commit()
        self.last_resolved = resolved
        return resolved

    def on_tick(
        self,
        directions: dict[str, str],
        confidences: dict[str, float],
        price: float | None,
        regime: str,
    ) -> None:
        """One scorecard step: record direction changes, then resolve due rows.

        Never raises -- any failure is captured in last_status.
        """
        if not self.cfg.enabled:
            self.last_status = "disabled"
            return
        if price is None or price <= 0:
            self.last_status = "no price this tick"
            return
        try:
            self.record(directions, confidences, price, regime)
            self.resolve(price)
            self.last_status = "ok"
        except sqlite3.Error as exc:
            self.last_status = f"sqlite error: {exc}"

    # ---- stats ---------------------------------------------------------

    def _rows_for(self, source: str) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                _RESOLVED_FOR_SOURCE_SQL, (self.symbol, source, int(self.cfg.window))
            )
            fetched = cur.fetchall()
        return [
            {
                "direction": r["direction"],
                "regime": r["regime"],
                "move_pct": r["move_pct"] if r["move_pct"] is not None else 0.0,
                "outcome": r["outcome"],
            }
            for r in fetched
        ]

    def snapshot(self) -> dict[str, Any]:
        """Per-voice rolling stats for /api/state. Never raises."""
        voices: dict[str, Any] = {}
        unresolved = 0
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM voice_signals "
                    "WHERE resolved = 0 AND symbol = ?",
                    (self.symbol,),
                )
                unresolved = int(cur.fetchone()["c"])
            for source in _SOURCES:
                rows = self._rows_for(source)
                stats = _stats_for_rows(rows)
                stats["by_regime"] = _regime_breakdown(rows)
                voices[source] = stats
        except sqlite3.Error as exc:
            self.last_status = f"sqlite error: {exc}"
        return {
            "status": self.last_status,
            "enabled": self.cfg.enabled,
            "symbol": self.symbol,
            "horizon_minutes": self.cfg.horizon_minutes,
            "min_move_pct": self.cfg.min_move_pct,
            "window": self.cfg.window,
            "unresolved": unresolved,
            "voices": voices,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
