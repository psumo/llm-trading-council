"""Per-symbol tracker invariant: one open position PER SYMBOL over a shared
global paper account.

Asserts that:
  * Two symbols can each hold an open position simultaneously.
  * A second judge verdict for a symbol that already has an open position does
    NOT open a second one (invariant holds per symbol).
  * Realized PnL from any symbol flows into the single global balance.
  * The store migration adds `symbol` and backfills legacy rows to BTCUSDT.
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TrackerCfg  # noqa: E402
from judge import JudgeResult  # noqa: E402
from paper_account import PaperAccount  # noqa: E402
from persistence import EventLog  # noqa: E402
from sources.base import Vote  # noqa: E402
from tracker import Tracker  # noqa: E402


def _cfg(tmp_path) -> TrackerCfg:
    return TrackerCfg(
        enabled=True,
        min_conviction=55.0,
        risk_pct=1.0,
        start_balance=1000.0,
        max_hold_hours=12.0,
        price_poll=False,  # use the orderflow-close fallback (no network)
        db_path=str(tmp_path / "positions.db"),
    )


def _judge(direction="LONG", entry=100.0, stop=95.0, tp=110.0, conv=70.0) -> JudgeResult:
    return JudgeResult(
        status="ok",
        direction=direction,
        entry_conviction=conv,  # entry_conviction gates the open
        conviction=conv,        # backward-compat alias
        entry=entry,
        stop_loss=stop,
        take_profit_1=tp,
        risk_reward=2.0,
        model="test",
    )


def _votes(close_price: float) -> dict[str, Vote]:
    # orderflow close drives the price fallback (price_poll disabled).
    return {
        "orderflow": Vote(
            source="orderflow",
            direction="long",
            confidence=0.8,
            extra={"close": close_price},
        ),
        "llm_tradebot": Vote(source="llm_tradebot", direction="long", confidence=0.7),
    }


def _notify(_t: str, _b: str) -> bool:
    return True


def test_one_open_position_per_symbol(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    account = PaperAccount(cfg.db_path, cfg.start_balance)
    events = EventLog(str(tmp_path / "events.jsonl"), 50)
    btc = Tracker(cfg, "BTCUSDT", account, events, _notify)
    eth = Tracker(cfg, "ETHUSDT", account, events, _notify)

    # Open a BTC position at price 100 (within tolerance of judge entry).
    btc.on_tick(_judge("LONG", entry=100.0, stop=95.0), _votes(100.0))
    assert btc.open_position is not None
    assert btc.open_position.symbol == "BTCUSDT"

    # ETH can open its OWN position concurrently -- invariant is per symbol.
    eth.on_tick(_judge("LONG", entry=50.0, stop=48.0, tp=56.0), _votes(50.0))
    assert eth.open_position is not None
    assert eth.open_position.symbol == "ETHUSDT"

    # Both open at once, distinct ids.
    assert btc.open_position.id != eth.open_position.id
    assert len(account.store.all_open_positions()) == 2

    # A fresh BTC verdict does NOT open a second BTC position.
    btc_id = btc.open_position.id
    btc.on_tick(_judge("LONG", entry=100.0, stop=95.0), _votes(101.0))
    assert btc.open_position.id == btc_id
    assert len([p for p in account.store.all_open_positions() if p.symbol == "BTCUSDT"]) == 1


def test_realized_pnl_flows_into_global_balance(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    account = PaperAccount(cfg.db_path, cfg.start_balance)
    events = EventLog(str(tmp_path / "events.jsonl"), 50)
    btc = Tracker(cfg, "BTCUSDT", account, events, _notify)

    start = account.balance
    # Open at 100, then hit take-profit (+2R) on the next tick. The second tick
    # carries a FLAT judge so the position closes at TP without immediately
    # reopening (a LONG judge would close-then-reopen in the same tick).
    btc.on_tick(_judge("LONG", entry=100.0, stop=95.0, tp=110.0), _votes(100.0))
    risk_usd = btc.open_position.risk_usd
    flat = JudgeResult(status="ok", direction="FLAT", conviction=0.0)
    btc.on_tick(flat, _votes(111.0))
    assert btc.open_position is None  # closed at TP, not reopened
    # TP 110 from entry 100, stop 95 -> (110-100)/5 = 2R GROSS. The tracker
    # charges round-trip fees (see tracker_models: 4.0 bps/side default), so the
    # realized balance lands just BELOW the 2R gross target. Assert the gain is
    # positive, close to 2R, and strictly less than gross by the (small) fee.
    gross_gain = 2.0 * risk_usd
    realized_gain = account.balance - start
    assert 0.0 < realized_gain < gross_gain
    assert gross_gain - realized_gain < 0.5  # round-trip fee is a small fraction of 2R


def test_store_migration_backfills_symbol(tmp_path) -> None:
    """A pre-multipair positions table (no `symbol` column) gains it on open and
    backfills legacy NULLs to BTCUSDT."""
    import sqlite3

    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    # The pre-multipair positions table: every column EXCEPT `symbol`.
    conn.execute(
        "CREATE TABLE positions ("
        "id INTEGER PRIMARY KEY, opened_at TEXT NOT NULL, direction TEXT NOT NULL, "
        "conviction REAL NOT NULL, entry REAL NOT NULL, stop_loss REAL NOT NULL, "
        "take_profit_1 REAL, take_profit_2 REAL, risk_reward REAL, rationale TEXT, "
        "source_dirs TEXT, context TEXT, risk_usd REAL, size_units REAL, "
        "judge_entry REAL, live_entry REAL, max_favorable REAL, max_adverse REAL, "
        "last_price REAL, closed_at TEXT, exit_price REAL, outcome TEXT, "
        "r_multiple REAL, pnl_pct REAL, pnl_usd REAL)"
    )
    conn.execute(
        "INSERT INTO positions (id, opened_at, direction, conviction, entry, "
        "stop_loss, closed_at, outcome, r_multiple) VALUES "
        "(1, '2026-01-01T00:00:00+00:00', 'LONG', 70.0, 100.0, 95.0, "
        "'2026-01-01T01:00:00+00:00', 'win', 2.0)"
    )
    conn.commit()
    conn.close()

    account = PaperAccount(db, 1000.0)
    cols = {
        r["name"]
        for r in account.store._conn.execute("PRAGMA table_info(positions)")
    }
    assert "symbol" in cols
    closed = account.store.closed_positions()
    assert len(closed) == 1
    assert closed[0].symbol == "BTCUSDT"
