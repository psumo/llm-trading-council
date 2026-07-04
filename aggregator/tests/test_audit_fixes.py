"""Tests for the audited correctness fixes.

Covers, one section per finding:
  * concurrent open from two threads -> no id collision, both rows present
  * fee-adjusted R (and r_gross) in realized_close, with env-var override
  * active_seconds freeze behavior (stale ticks do not accrue hold time)
  * judge offline-flap does NOT trigger a re-run
  * llm_trader raw_decode JSON extraction with multi-brace text
  * zero-balance busted state disables opening

No network: trackers run with price_poll disabled (orderflow-close fallback).
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import GuardsCfg, TrackerCfg  # noqa: E402
from judge import Judge, JudgeResult  # noqa: E402
from paper_account import PaperAccount  # noqa: E402
from persistence import EventLog  # noqa: E402
from sources.base import Vote, offline  # noqa: E402
from sources.llm_trader import _extract_analysis_json  # noqa: E402
from tracker import Tracker  # noqa: E402
from tracker_models import Position, realized_close  # noqa: E402


# --------------------------------------------------------------------------
# Finding 2: concurrent open -> no id collision, both rows present
# --------------------------------------------------------------------------


def _cfg(tmp_path) -> TrackerCfg:
    return TrackerCfg(
        enabled=True,
        min_conviction=55.0,
        risk_pct=1.0,
        start_balance=1000.0,
        max_hold_hours=12.0,
        price_poll=False,
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


# Pre-execution guards disabled for these low-level invariant tests (they open
# many concurrent positions / busted accounts that the guard chain would block).
_GUARDS_OFF = GuardsCfg(enabled=False)


def test_concurrent_open_no_id_collision(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    account = PaperAccount(cfg.db_path, cfg.start_balance)
    events = EventLog(str(tmp_path / "events.jsonl"), 200)

    symbols = [f"SYM{i}USDT" for i in range(12)]
    trackers = {
        s: Tracker(cfg, s, account, events, _notify, _GUARDS_OFF) for s in symbols
    }
    barrier = threading.Barrier(len(symbols))

    def _open(sym: str) -> None:
        barrier.wait()  # release all threads at once to maximise contention
        trackers[sym].on_tick(_judge("LONG", entry=100.0, stop=95.0), _votes(100.0))

    threads = [threading.Thread(target=_open, args=(s,)) for s in symbols]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    open_rows = account.store.all_open_positions()
    # Every symbol opened exactly one position.
    assert len(open_rows) == len(symbols)
    # All ids are distinct (no INSERT OR REPLACE overwrite).
    ids = [p.id for p in open_rows]
    assert len(set(ids)) == len(ids)
    # Every symbol is represented.
    assert {p.symbol for p in open_rows} == set(symbols)


# --------------------------------------------------------------------------
# Finding 4: fee-adjusted R
# --------------------------------------------------------------------------


def _sized_long() -> Position:
    # entry 100, stop 90 -> risk 10; risk_usd 10 -> size_units 1.0.
    return Position(
        id=1,
        opened_at="2026-06-12T00:00:00+00:00",
        direction="LONG",
        conviction=70.0,
        symbol="BTCUSDT",
        entry=100.0,
        stop_loss=90.0,
        take_profit_1=120.0,
        take_profit_2=None,
        risk_reward=2.0,
        rationale="test",
        risk_usd=10.0,
        size_units=1.0,
    )


def test_fee_zero_override_matches_gross(monkeypatch) -> None:
    monkeypatch.setenv("AGG_FEE_BPS_PER_SIDE", "0")
    closed = realized_close(_sized_long(), 120.0, "win", "2026-06-12T01:00:00+00:00")
    assert closed.r_gross == 2.0
    assert closed.r_multiple == 2.0  # no fees -> net == gross
    assert closed.pnl_usd == 20.0


def test_fee_subtracted_from_r(monkeypatch) -> None:
    monkeypatch.setenv("AGG_FEE_BPS_PER_SIDE", "4")
    pos = _sized_long()
    closed = realized_close(pos, 120.0, "win", "2026-06-12T01:00:00+00:00")
    # fee_usd = size_units * (entry + exit) * bps/10000
    #         = 1.0 * (100 + 120) * 4/10000 = 220 * 0.0004 = 0.088
    fee_usd = 1.0 * (100.0 + 120.0) * 4.0 / 10000.0
    assert closed.r_gross == 2.0
    assert abs(closed.r_multiple - (2.0 - fee_usd / 10.0)) < 1e-9
    assert closed.r_multiple < closed.r_gross  # fees make R worse
    assert abs(closed.pnl_usd - (2.0 * 10.0 - fee_usd)) < 1e-9


def test_fee_zero_size_no_fee(monkeypatch) -> None:
    # A position with size_units 0 (legacy fixtures) incurs no fee.
    from dataclasses import replace

    monkeypatch.setenv("AGG_FEE_BPS_PER_SIDE", "4")
    pos = replace(_sized_long(), size_units=0.0)
    closed = realized_close(pos, 120.0, "win", "2026-06-12T01:00:00+00:00")
    assert closed.r_multiple == closed.r_gross == 2.0


# --------------------------------------------------------------------------
# Finding 5: active_seconds freeze behavior
# --------------------------------------------------------------------------


def test_active_seconds_not_accrued_on_stale_ticks(tmp_path, monkeypatch) -> None:
    """A frozen (stale) price must not advance the live-hold clock, so a long
    off-hours gap cannot trigger the timeout close."""
    cfg = _cfg(tmp_path)
    # max_hold 0.001h = 3.6s; we will simulate large monotonic jumps.
    cfg = cfg.model_copy(update={"max_hold_hours": 0.001})
    account = PaperAccount(cfg.db_path, cfg.start_balance)
    events = EventLog(str(tmp_path / "events.jsonl"), 50)
    trk = Tracker(cfg, "BTCUSDT", account, events, _notify, _GUARDS_OFF)

    # Open a position on a live tick.
    trk.on_tick(_judge("LONG", entry=100.0, stop=95.0, tp=200.0), _votes(100.0))
    assert trk.open_position is not None
    opened_id = trk.open_position.id

    # Now force the price fetcher to report stale on subsequent ticks.
    class _StaleResult:
        price = 101.0
        status = "stale"
        source = "test"
        stale = True

    monkeypatch.setattr(trk.price, "get_price", lambda _c: _StaleResult())

    # Advance wall time well past max_hold; stale ticks must NOT close.
    flat = JudgeResult(status="ok", direction="FLAT", conviction=0.0)
    for _ in range(5):
        trk.on_tick(flat, _votes(101.0))
    assert trk.open_position is not None  # still open: frozen, no timeout
    assert trk.open_position.id == opened_id
    assert trk.open_position.active_seconds == 0.0  # no live time accrued


def test_active_seconds_accrues_on_live_ticks(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    account = PaperAccount(cfg.db_path, cfg.start_balance)
    events = EventLog(str(tmp_path / "events.jsonl"), 50)
    trk = Tracker(cfg, "BTCUSDT", account, events, _notify, _GUARDS_OFF)

    fake = {"t": 1000.0}
    monkeypatch.setattr("tracker.time.monotonic", lambda: fake["t"])

    trk.on_tick(_judge("LONG", entry=100.0, stop=95.0, tp=200.0), _votes(100.0))
    assert trk.open_position.active_seconds == 0.0  # first tick: no prior ts

    flat = JudgeResult(status="ok", direction="FLAT", conviction=0.0)
    fake["t"] = 1000.0 + 30.0  # 30s later, live price
    trk.on_tick(flat, _votes(101.0))
    assert trk.open_position is not None
    assert abs(trk.open_position.active_seconds - 30.0) < 1e-6


# --------------------------------------------------------------------------
# Finding 6: judge offline-flap does not trigger a re-run
# --------------------------------------------------------------------------


def _jcfg():
    from config import JudgeCfg

    return JudgeCfg(
        enabled=True,
        model="test-model",
        min_interval_seconds=1,
        max_age_seconds=10_000,
        timeout_seconds=5.0,
        api_key_env_path="unused.env",
    )


def test_offline_flap_does_not_trigger(monkeypatch) -> None:
    judge = Judge(cfg=_jcfg(), symbol="BTCUSDT")

    online = {
        "orderflow": Vote(source="orderflow", direction="long", confidence=0.8),
        "llm_trader": Vote(source="llm_trader", direction="long", confidence=0.7),
    }
    # First run establishes baseline.
    run, _ = judge.should_run(online, now=100.0)
    assert run is True
    # Simulate the call having happened: record dirs + call ts.
    judge._last_dirs = judge._carry_forward_online_dirs(online)
    judge._last_call_ts = 100.0

    # One source flaps offline (same underlying long stance) -> must NOT trigger.
    flapped = {
        "orderflow": offline("orderflow", "blip"),
        "llm_trader": Vote(source="llm_trader", direction="long", confidence=0.7),
    }
    run, reason = judge.should_run(flapped, now=101.0)
    assert run is False, reason

    # It comes back online still long -> still no change.
    run, reason = judge.should_run(online, now=102.0)
    assert run is False, reason

    # A genuine direction change DOES trigger.
    changed = {
        "orderflow": Vote(source="orderflow", direction="short", confidence=0.8),
        "llm_trader": Vote(source="llm_trader", direction="long", confidence=0.7),
    }
    run, reason = judge.should_run(changed, now=103.0)
    assert run is True
    assert reason == "source direction changed"


def test_last_call_ts_property() -> None:
    judge = Judge(cfg=_jcfg(), symbol="BTCUSDT")
    assert judge.last_call_ts == 0.0
    judge._last_call_ts = 1234.5
    assert judge.last_call_ts == 1234.5


# --------------------------------------------------------------------------
# Finding 7: raw_decode extraction with multi-brace text
# --------------------------------------------------------------------------


def test_extract_analysis_json_multi_brace() -> None:
    # Prose with a leading brace object, the real analysis object, and a
    # trailing brace object. Greedy {.*} would span all three and fail.
    text = (
        'note: {"unrelated": 1} then the model said '
        '{"analysis": {"signal": "BUY", "confidence": "high"}} '
        'and finally {"footer": true}'
    )
    blob = _extract_analysis_json(text)
    assert blob is not None
    assert blob["analysis"]["signal"] == "BUY"


def test_extract_analysis_json_skips_non_analysis_objects() -> None:
    text = '{"a": 1}{"b": 2}{"analysis": {"signal": "SELL"}}'
    blob = _extract_analysis_json(text)
    assert blob is not None
    assert blob["analysis"]["signal"] == "SELL"


def test_extract_analysis_json_none_when_absent() -> None:
    assert _extract_analysis_json("") is None
    assert _extract_analysis_json("no json here") is None
    assert _extract_analysis_json('{"no_analysis_key": 1}') is None


# --------------------------------------------------------------------------
# Finding 8: zero-balance busted state disables opening
# --------------------------------------------------------------------------


def test_busted_account_does_not_open(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    account = PaperAccount(cfg.db_path, cfg.start_balance)
    events = EventLog(str(tmp_path / "events.jsonl"), 50)
    trk = Tracker(cfg, "BTCUSDT", account, events, _notify, _GUARDS_OFF)

    # Drain the balance to zero.
    account.apply_pnl(-account.balance, None)
    assert account.is_busted is True
    assert trk.is_busted is True

    trk.on_tick(_judge("LONG", entry=100.0, stop=95.0), _votes(100.0))
    assert trk.open_position is None  # busted: no zombie zero-size trade
    assert account.store.all_open_positions() == []
    snap = trk.snapshot()
    assert snap["busted"] is True
