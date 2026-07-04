"""Per-instrument llm_trader path override.

Each single-pair llm-trader instance writes its own trade_history.db /
last_analysis.json. An instrument may set `llm_trader_paths` to point its
llm_trader voice at that instance; otherwise it falls back to the global
`llm_trader:` block (the original BTC instance).

Asserts:
  * An instrument WITH `llm_trader_paths` builds an LlmTraderSource pointed at
    the override paths (not the global ones).
  * previous_response.json is derived from the override's last_analysis dir.
  * An instrument WITHOUT the override falls back to the global block.
  * An InstrumentCfg with `llm_trader_paths` validates and round-trips.
"""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (  # noqa: E402
    Config,
    InstrumentCfg,
    LlmTraderPathsCfg,
)
from instrument import PerInstrument  # noqa: E402
from paper_account import PaperAccount  # noqa: E402
from persistence import EventLog  # noqa: E402


_GLOBAL_DB = "C:/global/data/trading/trade_history.db"
_GLOBAL_LA = "C:/global/data/trading/last_analysis.json"
_ETH_DB = "C:/inst/eth/data/trading/trade_history.db"
_ETH_LA = "C:/inst/eth/data/trading/last_analysis.json"


def _base_config_dict() -> dict:
    """Minimal valid aggregator config with two instruments: ETH overrides the
    llm_trader paths, BTC falls back to the global block."""
    return {
        "instruments": [
            {
                "symbol": "BTCUSDT",
                "timeframes": ["5m"],
                "voices": ["llm_trader"],
            },
            {
                "symbol": "ETHUSDT",
                "timeframes": ["5m"],
                "voices": ["llm_trader"],
                "llm_trader_paths": {
                    "db_path": _ETH_DB,
                    "last_analysis_path": _ETH_LA,
                },
            },
        ],
        "dashboard": {"host": "127.0.0.1", "port": 8500},
        "llm_trader": {
            "db_path": _GLOBAL_DB,
            "last_analysis_path": _GLOBAL_LA,
            "staleness_seconds": 1800,
        },
        "llm_tradebot": {"base_url": "http://x", "password": "p"},
        "orderflow": {"env_path": "C:/none/.env"},
        "confluence": {"alert_min_agree": 2, "strong_min_agree": 3},
        "notify": {},
        "persistence": {"events_path": "C:/none/events.jsonl"},
        "judge": {},
        "tracker": {"db_path": "C:/none/positions.db"},
        "scorecards": {},
        "reflection": {},
    }


def _make_instrument(cfg: Config, inst: InstrumentCfg, tmp_path: Path) -> PerInstrument:
    account = PaperAccount(str(tmp_path / "positions.db"), 1000.0)
    events = EventLog(str(tmp_path / "events.jsonl"), 10)
    return PerInstrument(
        cfg=cfg,
        inst=inst,
        account=account,
        events=events,
        notify=lambda _t, _b: True,
        memory_provider_factory=lambda _pi: (lambda: {}),
    )


def _find(cfg: Config, symbol: str) -> InstrumentCfg:
    return next(i for i in cfg.instruments if i.symbol == symbol)


def test_override_paths_reach_source(tmp_path: Path) -> None:
    cfg = Config(**_base_config_dict())
    eth = _find(cfg, "ETHUSDT")
    assert eth.llm_trader_paths is not None
    pi = _make_instrument(cfg, eth, tmp_path)
    assert pi.trader is not None
    assert pi.trader.db_path == Path(_ETH_DB)
    assert pi.trader.last_analysis_path == Path(_ETH_LA)
    # previous_response.json is derived from last_analysis_path's parent dir.
    derived = pi.trader.last_analysis_path.parent / "previous_response.json"
    assert derived == Path("C:/inst/eth/data/trading/previous_response.json")


def test_missing_override_falls_back_to_global(tmp_path: Path) -> None:
    cfg = Config(**_base_config_dict())
    btc = _find(cfg, "BTCUSDT")
    assert btc.llm_trader_paths is None
    pi = _make_instrument(cfg, btc, tmp_path)
    assert pi.trader is not None
    assert pi.trader.db_path == Path(_GLOBAL_DB)
    assert pi.trader.last_analysis_path == Path(_GLOBAL_LA)


def test_instrument_cfg_round_trips_override() -> None:
    inst = InstrumentCfg(
        symbol="solusdt",
        voices=["llm_trader"],
        llm_trader_paths=LlmTraderPathsCfg(
            db_path="C:/inst/sol/data/trading/trade_history.db",
            last_analysis_path="C:/inst/sol/data/trading/last_analysis.json",
        ),
    )
    assert inst.symbol == "SOLUSDT"  # validator upper-cases
    assert inst.llm_trader_paths is not None
    assert inst.llm_trader_paths.db_path.endswith("sol/data/trading/trade_history.db")
