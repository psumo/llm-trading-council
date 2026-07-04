"""
LLM-TradeBot Backtesting System
================================

回测系统模块，支持：
- 历史数据回放
- 策略性能评估
- 可视化分析报告

Author: AI Trader Team
Date: 2025-12-31
"""

from src.backtest.data_replay import DataReplayAgent
from src.backtest.portfolio import BacktestPortfolio, Position, Trade
from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import PerformanceMetrics
from src.backtest.report import BacktestReport

__all__ = [
    'DataReplayAgent',
    'BacktestPortfolio',
    'Position',
    'Trade',
    'BacktestEngine',
    'BacktestResult',
    'PerformanceMetrics',
    'BacktestReport',
]
