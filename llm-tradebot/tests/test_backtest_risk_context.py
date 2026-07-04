"""
Tests for backtest risk context parity with live pipeline.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.data_sync_agent import MarketSnapshot
from src.backtest.agent_wrapper import BacktestAgentRunner
from src.backtest.engine import BacktestConfig, BacktestEngine
from src.backtest.portfolio import Side, Trade


def _build_snapshot(periods: int = 1600) -> MarketSnapshot:
    idx = pd.date_range("2026-01-01", periods=periods, freq="5min")
    price = np.linspace(1.0, 1.2, periods) + np.random.normal(0, 0.003, periods)
    df_5m = pd.DataFrame(
        {
            "open": price,
            "high": price + 0.01,
            "low": price - 0.01,
            "close": price,
            "volume": np.random.uniform(100, 500, periods),
        },
        index=idx,
    )
    df_15m = (
        df_5m.resample("15min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    df_1h = (
        df_5m.resample("1h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    return MarketSnapshot(
        stable_5m=df_5m,
        stable_15m=df_15m,
        stable_1h=df_1h,
        live_5m={"open": float(price[-1]), "close": float(price[-1])},
        live_15m={},
        live_1h={},
        timestamp=idx[-1],
        alignment_ok=True,
        fetch_duration=0,
    )


def test_backtest_runner_emits_position_1h_context():
    runner = BacktestAgentRunner({"use_llm": False})
    snapshot = _build_snapshot()

    decision = asyncio.run(runner.step(snapshot, None))

    assert "position_1h" in decision
    assert isinstance(decision["position_1h"], dict)
    assert "allow_long" in decision["position_1h"]
    assert "allow_short" in decision["position_1h"]


def test_backtest_engine_directional_trade_stats():
    config = BacktestConfig(
        symbol="BTCUSDT",
        start_date="2026-01-01",
        end_date="2026-01-03",
        strategy_mode="technical",
    )
    engine = BacktestEngine(config)

    now = datetime(2026, 1, 3, 0, 0)
    trades = [
        Trade(trade_id=1, symbol="BTCUSDT", side=Side.LONG, action="close", quantity=1, price=100, timestamp=now - timedelta(hours=5), pnl=5.0),
        Trade(trade_id=2, symbol="BTCUSDT", side=Side.SHORT, action="close", quantity=1, price=100, timestamp=now - timedelta(hours=4), pnl=7.0),
        Trade(trade_id=3, symbol="BTCUSDT", side=Side.LONG, action="close", quantity=1, price=100, timestamp=now - timedelta(hours=3), pnl=-3.0),
        Trade(trade_id=4, symbol="BTCUSDT", side=Side.LONG, action="close", quantity=1, price=100, timestamp=now - timedelta(hours=2), pnl=-2.0),
        Trade(trade_id=5, symbol="BTCUSDT", side=Side.SHORT, action="close", quantity=1, price=100, timestamp=now - timedelta(hours=1), pnl=-1.0),
    ]
    engine.portfolio = SimpleNamespace(trades=trades)

    stats = engine._get_symbol_trade_stats("BTCUSDT", max_trades=5)

    assert stats["symbol_loss_streak"] == 3
    assert stats["symbol_long_loss_streak"] == 2
    assert stats["symbol_short_loss_streak"] == 1
    assert stats["symbol_long_recent_trades"] == 3
    assert stats["symbol_short_recent_trades"] == 2
