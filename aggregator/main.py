"""Signal-Confluence Aggregator entrypoint.

Single FastAPI service: a background polling loop reads three signal sources,
the confluence engine combines their (staleness-decayed) votes, alerts fire as
Windows toasts with dedupe/cooldown, every event is appended to events.jsonl,
and a dark dashboard is served at the configured port.

A dead source can never crash the loop -- each source.poll() returns an offline
vote on any failure and the loop body is wrapped defensively.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from config import Config, load_config
from confluence import Confluence
from dashboard import DASHBOARD_HTML
from instrument import PerInstrument
from journal import build_journal
from judge import JudgeResult
from lessons import LessonsStore
from notify import Notifier, backend_name
from paper_account import PaperAccount
from persistence import EventLog
from reflection import Reflector
from sources.base import Vote
from tracker_stats import compute_stats

CONFIG_PATH = Path(__file__).with_name("config.yaml")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _vote_to_dict(v: Vote) -> dict[str, Any]:
    return {
        "source": v.source,
        "direction": v.direction,
        "confidence": v.confidence,
        "age_seconds": v.age_seconds,
        "detail": v.detail,
        "extra": v.extra,
    }


def _conf_to_dict(c: Confluence) -> dict[str, Any]:
    return {
        "direction": c.direction,
        "level": c.level,
        "agree_count": c.agree_count,
        "online_count": c.online_count,
        "score": c.score,
        "sizing_note": c.sizing_note,
    }


class Aggregator:
    """Owns the shared paper account, every per-instrument engine, the global
    learning layer (lessons/reflection), and the polling loop."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.events = EventLog(cfg.persistence.events_path, cfg.persistence.max_log_events)
        self.notifier = Notifier(cfg.notify.toast_app_id, cfg.notify.enabled)

        # Shared GLOBAL paper account (one balance, one equity curve, one db).
        self.account = PaperAccount(cfg.tracker.db_path, cfg.tracker.start_balance)

        # Lessons store + reflection pass are GLOBAL (one across all symbols).
        self.lessons = LessonsStore.load(cfg.reflection.lessons_path)
        self.reflector = Reflector(cfg.reflection, cfg.judge)
        self.last_reflection: dict[str, Any] = {"status": "starting", "reason": ""}

        # One engine per configured instrument.
        self.instruments: list[PerInstrument] = [
            PerInstrument(
                cfg=cfg,
                inst=inst,
                account=self.account,
                events=self.events,
                notify=self.notifier.send,
                memory_provider_factory=self._memory_provider_for,
            )
            for inst in cfg.instruments
        ]
        self.by_symbol: dict[str, PerInstrument] = {
            eng.symbol: eng for eng in self.instruments
        }

        self.state: dict[str, Any] = self._initial_state()

    # ---- global learning layer -----------------------------------------

    def _memory_provider_for(self, eng: PerInstrument) -> Any:
        """Build the judge MEMORY provider for one instrument: that symbol's own
        recent trades + per-voice scorecards, plus the GLOBAL lessons."""

        def provider() -> dict[str, Any]:
            try:
                regime = eng.current_regime()
                return {
                    "recent_trades": eng.recent_trade_memory(),
                    "scorecards": eng.scorecard_memory(regime),
                    "lessons": [le.text for le in self.lessons.active()],
                }
            except Exception:
                return {}

        return provider

    def _run_reflection(self) -> None:
        """Run the global reflection pass if due (over ALL symbols' closed
        trades); record an event; never raises."""
        try:
            closed = self.account.store.closed_positions()
            result = self.reflector.maybe_run(closed, self.lessons)
            self.last_reflection = result.to_dict()
            if result.status == "ok":
                self.events.append(
                    "REFLECTION",
                    {
                        "summary": (
                            f"reflection: +{result.added} lessons, "
                            f"-{result.retired} retired ({result.auto_retired} auto). "
                            f"{result.summary}"
                        ),
                        "reflection": result.to_dict(),
                    },
                )
        except Exception as exc:  # reflection must never crash the loop
            self.last_reflection = {"status": "error", "error": str(exc)}

    # ---- global account snapshot ---------------------------------------

    def _account_snapshot(self) -> dict[str, Any]:
        """Whole-account performance (all symbols) for the global PERFORMANCE
        strip, plus every open position (one per symbol possible)."""
        store = self.account.store
        closed = store.closed_positions()
        curve = store.equity_curve()
        stats = compute_stats(
            closed, curve, self.account.balance, self.cfg.tracker.start_balance
        )
        open_positions: list[dict[str, Any]] = []
        for eng in self.instruments:
            view = eng.tracker._open_position_view()
            if view is not None:
                open_positions.append(view)
        # Last closed across all symbols (already newest-first from the store).
        recent = [p.to_dict() for p in closed[:10]]
        # Per-symbol price status for the strip.
        prices = {
            eng.symbol: {
                "last_price": eng.tracker.last_price,
                "price_status": eng.tracker.last_price_status,
                "price_source": eng.tracker.last_price_source,
            }
            for eng in self.instruments
        }
        return {
            "enabled": self.cfg.tracker.enabled,
            "balance": round(self.account.balance, 2),
            "stats": stats,
            "open_positions": open_positions,
            "open_position": open_positions[0] if open_positions else None,
            "recent_closed": recent,
            "prices": prices,
            # Back-compat fields used by the existing perf strip.
            "last_price": (
                self.instruments[0].tracker.last_price if self.instruments else None
            ),
            "price_status": (
                self.instruments[0].tracker.last_price_status
                if self.instruments
                else "starting"
            ),
            "price_source": (
                self.instruments[0].tracker.last_price_source
                if self.instruments
                else "none"
            ),
        }

    def _initial_state(self) -> dict[str, Any]:
        instruments: dict[str, Any] = {}
        for eng in self.instruments:
            instruments[eng.symbol] = {
                "symbol": eng.symbol,
                "voices": eng.voices,
                "votes": [],
                "confluence": _conf_to_dict(
                    Confluence("neutral", "none", 0, 0, 0.0, "starting up", [])
                ),
                "judge": JudgeResult(status="starting").to_dict(),
                "tracker": eng.tracker.snapshot(),
                "scorecards": eng.scorecards.snapshot(),
            }
        return {
            "symbols": [eng.symbol for eng in self.instruments],
            "symbol": self.cfg.primary_symbol,
            "updated_at": _now_iso(),
            "toast_backend": backend_name(),
            "tracker": self._account_snapshot(),
            "instruments": instruments,
            "lessons": [le.to_dict() for le in self.lessons.active()],
            "reflection": self.last_reflection,
            "events": [],
        }

    # ---- per-instrument tick -------------------------------------------

    async def _tick_instrument(self, eng: PerInstrument) -> dict[str, Any]:
        """Run one full tick for a single instrument. Any failure degrades only
        this instrument (returns a degraded state dict, logs a LOOP_ERROR)."""
        try:
            votes = await eng.poll_votes()
            conf = eng.confluence(votes)
            # Judge (blocking Gemini call when triggered) off the event loop.
            judge_result, fresh = await asyncio.to_thread(eng.run_judge, votes)
            if fresh:
                self.events.append(
                    "JUDGE",
                    {
                        "summary": (
                            f"{eng.symbol} {judge_result.direction} "
                            f"conv={judge_result.conviction:.0f} "
                            f"entry={judge_result.entry} sl={judge_result.stop_loss} "
                            f"tp1={judge_result.take_profit_1} "
                            f"align={judge_result.tf_alignment}"
                        ),
                        "symbol": eng.symbol,
                        "judge": judge_result.to_dict(),
                    },
                )
                eng.maybe_judge_alert(judge_result)
            # Paper tracker (price fetch + monitor/open) off the event loop.
            await asyncio.to_thread(eng.update_tracker, judge_result, votes)
            # Per-voice scorecards.
            await asyncio.to_thread(eng.scorecards_tick, votes)
            # Periodic per-symbol signal snapshot.
            self.events.append(
                "SIGNAL",
                {
                    "summary": (
                        f"{eng.symbol} {conf.direction}/{conf.level} "
                        f"{conf.agree_count}/{conf.online_count} "
                        + ", ".join(f"{v.source}:{v.direction}" for v in votes)
                    ),
                    "symbol": eng.symbol,
                    "confluence": _conf_to_dict(conf),
                    "votes": [_vote_to_dict(v) for v in votes],
                },
            )
            return eng.state(votes, conf, judge_result)
        except Exception as exc:  # one symbol failing must not affect others
            self.events.append(
                "LOOP_ERROR",
                {"summary": f"{eng.symbol} tick failed: {exc}", "symbol": eng.symbol},
            )
            prev = self.state.get("instruments", {}).get(eng.symbol, {})
            return prev or {
                "symbol": eng.symbol,
                "voices": eng.voices,
                "votes": [],
                "confluence": _conf_to_dict(
                    Confluence("neutral", "none", 0, 0, 0.0, "error", [])
                ),
                "judge": JudgeResult(status="error", error=str(exc)).to_dict(),
                "tracker": eng.tracker.snapshot(),
                "scorecards": eng.scorecards.snapshot(),
            }

    async def loop(self) -> None:
        symbols = ", ".join(eng.symbol for eng in self.instruments)
        self.events.append(
            "STARTUP",
            {"summary": f"aggregator online for [{symbols}]; toast backend={backend_name()}"},
        )
        while True:
            try:
                # Each instrument ticks independently; gather them concurrently
                # so one symbol's blocking judge/price call doesn't serialise the
                # others. A per-instrument failure is contained in _tick_instrument.
                results = await asyncio.gather(
                    *(self._tick_instrument(eng) for eng in self.instruments)
                )
                instruments = {
                    eng.symbol: res for eng, res in zip(self.instruments, results)
                }
                # Global reflection pass (over all symbols) when due.
                await asyncio.to_thread(self._run_reflection)
                self.state = {
                    "symbols": [eng.symbol for eng in self.instruments],
                    "symbol": self.cfg.primary_symbol,
                    "updated_at": _now_iso(),
                    "toast_backend": backend_name(),
                    "tracker": self._account_snapshot(),
                    "instruments": instruments,
                    "lessons": [le.to_dict() for le in self.lessons.active()],
                    "reflection": self.last_reflection,
                    "events": self.events.recent(),
                }
            except Exception as exc:  # last-resort guard; loop must survive
                self.events.append("LOOP_ERROR", {"summary": f"loop iteration failed: {exc}"})
            await asyncio.sleep(self.cfg.poll_interval_seconds)


def build_app(agg: Aggregator) -> FastAPI:
    app = FastAPI(title="Confluence Aggregator", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/api/state")
    async def state() -> JSONResponse:
        return JSONResponse(agg.state)

    @app.get("/api/journal")
    async def journal(symbol: str | None = None) -> JSONResponse:
        closed = agg.account.store.closed_positions()
        return JSONResponse(build_journal(closed, symbol))

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "symbol": agg.cfg.primary_symbol,
                "symbols": [eng.symbol for eng in agg.instruments],
            }
        )

    @app.on_event("startup")
    async def _start() -> None:
        app.state.loop_task = asyncio.create_task(agg.loop())

    @app.on_event("shutdown")
    async def _stop() -> None:
        task = getattr(app.state, "loop_task", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return app


def main() -> None:
    cfg = load_config(CONFIG_PATH)
    agg = Aggregator(cfg)
    app = build_app(agg)
    symbols = ", ".join(eng.symbol for eng in agg.instruments)
    print(f"[aggregator] [{symbols}] dashboard -> http://{cfg.dashboard.host}:{cfg.dashboard.port}")
    print(f"[aggregator] toast backend: {backend_name()}")
    uvicorn.run(app, host=cfg.dashboard.host, port=cfg.dashboard.port, log_level="warning")


if __name__ == "__main__":
    main()
