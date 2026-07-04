"""Shared paper account for the multi-symbol tracker.

The paper account is GLOBAL: one balance, one equity curve, one positions table
(SQLite). Per-symbol `Tracker` instances open/close positions through this
shared account, so risk is sized off the single global balance and the open /
realized PnL of every symbol flows into the same equity curve.

Thread-safety: a lock guards balance mutation + equity append because per-symbol
trackers run their on_tick work off the event loop via asyncio.to_thread.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from tracker_store import TrackerStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperAccount:
    """Owns the shared balance, equity curve and the (shared) TrackerStore."""

    def __init__(self, db_path: str, start_balance: float):
        self.store = TrackerStore(db_path)
        self.start_balance = start_balance
        self._lock = threading.Lock()
        self.balance = self.store.latest_balance(start_balance)
        # Seed the equity curve on first ever run so stats have a baseline.
        if not self.store.equity_curve():
            self.store.record_equity(_now_iso(), self.balance)

    def apply_pnl(self, pnl_usd: float, closed_at: str | None) -> float:
        """Apply a realized PnL to the global balance, record equity, return the
        new balance. Thread-safe."""
        with self._lock:
            self.balance = max(0.0, self.balance + pnl_usd)
            self.store.record_equity(closed_at or _now_iso(), self.balance)
            return self.balance

    def risk_usd(self, risk_pct: float) -> float:
        """USD risked for a new trade: risk_pct of the current global balance."""
        with self._lock:
            return self.balance * (risk_pct / 100.0)

    @property
    def is_busted(self) -> bool:
        """The account is busted when the global balance has reached zero.
        Trackers must not open positions while busted (a zero balance sizes a
        zero-unit zombie trade)."""
        with self._lock:
            return self.balance <= 0.0

    def next_id(self) -> int:
        with self._lock:
            return self.store.next_id()
