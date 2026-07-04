"""SQLite persistence for the paper-trading tracker (stdlib sqlite3, WAL).

Two tables:
  positions(id, ... all Position fields ...)
  equity(ts, balance)

All writes are parameterized. On startup the store can reload the single open
position (one-open-position invariant) and the latest balance so the tracker
survives an aggregator restart. JSON columns (source_dirs) are stored as text.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from tracker_models import Position

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id              INTEGER PRIMARY KEY,
    opened_at       TEXT NOT NULL,
    direction       TEXT NOT NULL,
    conviction      REAL NOT NULL,
    symbol          TEXT NOT NULL DEFAULT 'BTCUSDT',
    entry           REAL NOT NULL,
    stop_loss       REAL NOT NULL,
    take_profit_1   REAL,
    take_profit_2   REAL,
    risk_reward     REAL,
    rationale       TEXT,
    source_dirs     TEXT,
    context         TEXT,
    risk_usd        REAL,
    size_units      REAL,
    judge_entry     REAL,
    live_entry      REAL,
    max_favorable   REAL,
    max_adverse     REAL,
    last_price      REAL,
    closed_at       TEXT,
    exit_price      REAL,
    outcome         TEXT,
    r_multiple      REAL,
    pnl_pct         REAL,
    pnl_usd         REAL,
    r_gross         REAL,
    active_seconds  REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS equity (
    ts      TEXT NOT NULL,
    balance REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_positions_closed ON positions(closed_at);
"""

# Static, fully-literal SQL strings (no runtime composition) so the column
# list can never carry untrusted input into a query.
_COLS = (
    "id, opened_at, direction, conviction, symbol, entry, stop_loss, "
    "take_profit_1, take_profit_2, risk_reward, rationale, source_dirs, "
    "context, risk_usd, size_units, judge_entry, live_entry, max_favorable, "
    "max_adverse, last_price, closed_at, exit_price, outcome, r_multiple, "
    "pnl_pct, pnl_usd, r_gross, active_seconds"
)
# Columns minus the leading `id` (id is allocated by AUTOINCREMENT on insert of
# a NEW row; existing rows are updated by id, never re-inserted).
_COLS_NO_ID = (
    "opened_at, direction, conviction, symbol, entry, stop_loss, "
    "take_profit_1, take_profit_2, risk_reward, rationale, source_dirs, "
    "context, risk_usd, size_units, judge_entry, live_entry, max_favorable, "
    "max_adverse, last_price, closed_at, exit_price, outcome, r_multiple, "
    "pnl_pct, pnl_usd, r_gross, active_seconds"
)
# Plain INSERT (no OR REPLACE): a NULL id lets SQLite's INTEGER PRIMARY KEY
# assign a fresh rowid, so two concurrent opens can never collide on id.
_INSERT_NEW_SQL = (
    "INSERT INTO positions "
    f"({_COLS_NO_ID}) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
# UPDATE an existing row in place (used for excursion updates and closes).
_UPDATE_SQL = (
    "UPDATE positions SET "
    "opened_at = ?, direction = ?, conviction = ?, symbol = ?, entry = ?, "
    "stop_loss = ?, take_profit_1 = ?, take_profit_2 = ?, risk_reward = ?, "
    "rationale = ?, source_dirs = ?, context = ?, risk_usd = ?, size_units = ?, "
    "judge_entry = ?, live_entry = ?, max_favorable = ?, max_adverse = ?, "
    "last_price = ?, closed_at = ?, exit_price = ?, outcome = ?, r_multiple = ?, "
    "pnl_pct = ?, pnl_usd = ?, r_gross = ?, active_seconds = ? "
    "WHERE id = ?"
)
_SELECT_OPEN_SQL = (
    f"SELECT {_COLS} FROM positions "
    "WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
)
_SELECT_OPEN_FOR_SYMBOL_SQL = (
    f"SELECT {_COLS} FROM positions "
    "WHERE closed_at IS NULL AND symbol = ? ORDER BY id DESC LIMIT 1"
)
_SELECT_ALL_OPEN_SQL = (
    f"SELECT {_COLS} FROM positions "
    "WHERE closed_at IS NULL ORDER BY id DESC"
)
_SELECT_CLOSED_SQL = (
    f"SELECT {_COLS} FROM positions "
    "WHERE closed_at IS NOT NULL ORDER BY id DESC"
)
_SELECT_CLOSED_LIMIT_SQL = (
    f"SELECT {_COLS} FROM positions "
    "WHERE closed_at IS NOT NULL ORDER BY id DESC LIMIT ?"
)
_SELECT_CLOSED_FOR_SYMBOL_SQL = (
    f"SELECT {_COLS} FROM positions "
    "WHERE closed_at IS NOT NULL AND symbol = ? ORDER BY id DESC"
)


def _row_value(row: sqlite3.Row, key: str) -> Any:
    """Safe column access -- a row may predate a migrated column."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _row_to_position(row: sqlite3.Row) -> Position:
    raw_dirs = row["source_dirs"]
    try:
        source_dirs = json.loads(raw_dirs) if raw_dirs else {}
    except (json.JSONDecodeError, TypeError):
        source_dirs = {}
    raw_ctx = _row_value(row, "context")
    try:
        context = json.loads(raw_ctx) if raw_ctx else {}
    except (json.JSONDecodeError, TypeError):
        context = {}
    return Position(
        id=row["id"],
        opened_at=row["opened_at"],
        direction=row["direction"],
        conviction=row["conviction"],
        symbol=_row_value(row, "symbol") or "BTCUSDT",
        entry=row["entry"],
        stop_loss=row["stop_loss"],
        take_profit_1=row["take_profit_1"],
        take_profit_2=row["take_profit_2"],
        risk_reward=row["risk_reward"],
        rationale=row["rationale"] or "",
        source_dirs=source_dirs,
        context=context,
        risk_usd=row["risk_usd"] or 0.0,
        size_units=row["size_units"] or 0.0,
        judge_entry=row["judge_entry"],
        live_entry=row["live_entry"],
        max_favorable=row["max_favorable"] or 0.0,
        max_adverse=row["max_adverse"] or 0.0,
        last_price=row["last_price"],
        closed_at=row["closed_at"],
        exit_price=row["exit_price"],
        outcome=row["outcome"],
        r_multiple=row["r_multiple"],
        pnl_pct=row["pnl_pct"],
        pnl_usd=row["pnl_usd"],
        r_gross=_row_value(row, "r_gross"),
        active_seconds=_row_value(row, "active_seconds") or 0.0,
    )


class TrackerStore:
    """Owns the SQLite connection and all read/write SQL for the tracker."""

    def __init__(self, db_path: str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The single connection is shared across every per-symbol tracker, whose
        # on_tick work runs in parallel worker threads (asyncio.to_thread +
        # gather). sqlite3 connections are NOT thread-safe for concurrent use,
        # so a reentrant lock serializes every execute/commit/fetch on _conn.
        self._lock = threading.RLock()
        # check_same_thread=False: the polling loop runs source work via
        # asyncio.to_thread, so store calls may arrive from a worker thread.
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            # Wait (up to 5s) instead of erroring when another connection (e.g.
            # the Scorecards connection to the same file) holds a write lock.
            self._conn.execute("PRAGMA busy_timeout=5000;")
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the table first shipped, in place.

        Idempotent: existing rows are preserved (new column is NULL). Never
        drops or rewrites data. `context` (entry-condition snapshot) was added
        for the journal/learning layer.
        """
        cur = self._conn.execute("PRAGMA table_info(positions)")
        cols = {row["name"] for row in cur.fetchall()}
        if "context" not in cols:
            # ALTER TABLE ADD COLUMN with a static, fully-literal statement.
            self._conn.execute("ALTER TABLE positions ADD COLUMN context TEXT")
        if "r_gross" not in cols:
            # Gross (pre-fee) R, added with the fee-aware close model. Existing
            # rows keep NULL (their r_multiple predates fees); never rewritten.
            self._conn.execute("ALTER TABLE positions ADD COLUMN r_gross REAL")
        if "active_seconds" not in cols:
            # Live-market hold time. Default 0 so legacy rows are unaffected.
            self._conn.execute(
                "ALTER TABLE positions ADD COLUMN active_seconds REAL DEFAULT 0"
            )
        if "symbol" not in cols:
            # Multi-pair migration: existing rows predate per-symbol tracking,
            # so they are all BTCUSDT. Add the column with that default and
            # backfill any NULLs idempotently.
            self._conn.execute(
                "ALTER TABLE positions ADD COLUMN symbol TEXT NOT NULL "
                "DEFAULT 'BTCUSDT'"
            )
        self._conn.execute(
            "UPDATE positions SET symbol = 'BTCUSDT' "
            "WHERE symbol IS NULL OR symbol = ''"
        )

    def _values_no_id(self, pos: Position) -> tuple[Any, ...]:
        """Column values in _COLS_NO_ID order (for a NEW-row INSERT)."""
        return (
            pos.opened_at,
            pos.direction,
            pos.conviction,
            pos.symbol,
            pos.entry,
            pos.stop_loss,
            pos.take_profit_1,
            pos.take_profit_2,
            pos.risk_reward,
            pos.rationale,
            json.dumps(pos.source_dirs),
            json.dumps(pos.context),
            pos.risk_usd,
            pos.size_units,
            pos.judge_entry,
            pos.live_entry,
            pos.max_favorable,
            pos.max_adverse,
            pos.last_price,
            pos.closed_at,
            pos.exit_price,
            pos.outcome,
            pos.r_multiple,
            pos.pnl_pct,
            pos.pnl_usd,
            pos.r_gross,
            pos.active_seconds,
        )

    def open_position_atomic(self, pos: Position) -> Position:
        """Insert a NEW position and return a copy carrying the id SQLite
        assigned. Allocation + insert happen inside one lock-guarded critical
        section so two concurrent opens can never share an id.
        """
        with self._lock:
            cur = self._conn.execute(_INSERT_NEW_SQL, self._values_no_id(pos))
            new_id = int(cur.lastrowid or 0)
            self._conn.commit()
        from dataclasses import replace

        return replace(pos, id=new_id)

    def update_position(self, pos: Position) -> None:
        """Update an existing row (excursion change or close) by id."""
        with self._lock:
            self._conn.execute(
                _UPDATE_SQL, (*self._values_no_id(pos), pos.id)
            )
            self._conn.commit()

    def upsert_position(self, pos: Position) -> None:
        """Persist a position: INSERT a new row (id<=0) or UPDATE by id.

        Replaces the old INSERT OR REPLACE: new rows take a fresh AUTOINCREMENT
        id (no collisions), existing rows are updated in place so a stale id can
        never silently overwrite another symbol's position.
        """
        with self._lock:
            if pos.id and pos.id > 0:
                self._conn.execute(
                    _UPDATE_SQL, (*self._values_no_id(pos), pos.id)
                )
            else:
                self._conn.execute(_INSERT_NEW_SQL, self._values_no_id(pos))
            self._conn.commit()

    def next_id(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS m FROM positions"
            )
            return int(cur.fetchone()["m"]) + 1

    def load_open_position(self) -> Position | None:
        with self._lock:
            cur = self._conn.execute(_SELECT_OPEN_SQL)
            row = cur.fetchone()
        return _row_to_position(row) if row else None

    def load_open_position_for_symbol(self, symbol: str) -> Position | None:
        with self._lock:
            cur = self._conn.execute(_SELECT_OPEN_FOR_SYMBOL_SQL, (symbol,))
            row = cur.fetchone()
        return _row_to_position(row) if row else None

    def all_open_positions(self) -> list[Position]:
        with self._lock:
            cur = self._conn.execute(_SELECT_ALL_OPEN_SQL)
            rows = cur.fetchall()
        return [_row_to_position(r) for r in rows]

    def closed_positions(self, limit: int | None = None) -> list[Position]:
        with self._lock:
            if limit is not None:
                cur = self._conn.execute(_SELECT_CLOSED_LIMIT_SQL, (int(limit),))
            else:
                cur = self._conn.execute(_SELECT_CLOSED_SQL)
            rows = cur.fetchall()
        return [_row_to_position(r) for r in rows]

    def closed_positions_for_symbol(self, symbol: str) -> list[Position]:
        with self._lock:
            cur = self._conn.execute(_SELECT_CLOSED_FOR_SYMBOL_SQL, (symbol,))
            rows = cur.fetchall()
        return [_row_to_position(r) for r in rows]

    def recent_closed(self, limit: int = 10) -> list[dict[str, Any]]:
        """Recent closed trades across ALL symbols, newest first.

        Returns compact dicts (closed_at, r_multiple, symbol) for the guard
        pipeline -- ordered by closed_at descending. Lock-guarded, parameterized.
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT closed_at, r_multiple, symbol FROM positions "
                "WHERE closed_at IS NOT NULL "
                "ORDER BY closed_at DESC LIMIT ?",
                (int(limit),),
            )
            rows = cur.fetchall()
        return [
            {
                "closed_at": r["closed_at"],
                "r_multiple": r["r_multiple"],
                "symbol": r["symbol"],
            }
            for r in rows
        ]

    def count_open(self) -> int:
        """Number of currently-open positions across ALL symbols."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n FROM positions WHERE closed_at IS NULL"
            )
            return int(cur.fetchone()["n"])

    def record_equity(self, ts: str, balance: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO equity (ts, balance) VALUES (?, ?)", (ts, balance)
            )
            self._conn.commit()

    def equity_curve(self) -> list[tuple[str, float]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, balance FROM equity ORDER BY rowid ASC"
            )
            rows = cur.fetchall()
        return [(r["ts"], r["balance"]) for r in rows]

    def latest_balance(self, default: float) -> float:
        with self._lock:
            cur = self._conn.execute(
                "SELECT balance FROM equity ORDER BY rowid DESC LIMIT 1"
            )
            row = cur.fetchone()
        return float(row["balance"]) if row else default

    def close(self) -> None:
        with self._lock:
            self._conn.close()
