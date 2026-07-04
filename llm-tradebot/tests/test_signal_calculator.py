"""
测试信号计算器功能
"""
import pytest
import pandas as pd
import numpy as np
from src.backtest.agent_wrapper import BacktestSignalCalculator


def test_rsi_no_division_by_zero():
    """测试RSI计算不会除零"""
    calc = BacktestSignalCalculator()
    
    # 创建全零变化的数据（会导致loss=0）
    data = pd.Series([100.0] * 50)
    
    # 不应该抛出异常
    rsi = calc.calculate_rsi(data)
    
    # RSI应该是有效值（不是NaN或Inf）
    assert not rsi.isna().all(), "RSI should not be all NaN"
    assert not np.isinf(rsi).any(), "RSI should not contain infinity"


def test_rsi_normal_calculation():
    """测试RSI正常计算"""
    calc = BacktestSignalCalculator()
    
    # 创建有变化的数据
    data = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109] * 5)
    
    rsi = calc.calculate_rsi(data, period=14)
    
    # RSI应该在0-100之间
    valid_rsi = rsi.dropna()
    assert (valid_rsi >= 0).all(), "RSI should be >= 0"
    assert (valid_rsi <= 100).all(), "RSI should be <= 100"


def test_rsi_uptrend():
    """测试上升趋势的RSI"""
    calc = BacktestSignalCalculator()
    
    # 创建上升趋势数据
    data = pd.Series(range(100, 150))
    
    rsi = calc.calculate_rsi(data, period=14)
    
    # 上升趋势RSI应该偏高
    valid_rsi = rsi.dropna()
    assert valid_rsi.mean() > 50, "Uptrend RSI should be above 50"


def test_rsi_downtrend():
    """测试下降趋势的RSI"""
    calc = BacktestSignalCalculator()
    
    # 创建下降趋势数据
    data = pd.Series(range(150, 100, -1))
    
    rsi = calc.calculate_rsi(data, period=14)
    
    # 下降趋势RSI应该偏低
    valid_rsi = rsi.dropna()
    assert valid_rsi.mean() < 50, "Downtrend RSI should be below 50"


def test_ema_calculation():
    """测试EMA计算"""
    calc = BacktestSignalCalculator()
    
    data = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109] * 5)
    
    ema = calc.calculate_ema(data, span=20)
    
    # EMA应该是有效值
    assert not ema.isna().all(), "EMA should not be all NaN"
    assert len(ema) == len(data), "EMA length should match input"


def test_kdj_calculation():
    """测试KDJ计算"""
    calc = BacktestSignalCalculator()
    
    # 创建测试数据
    high = pd.Series([105, 107, 106, 108, 110, 109, 111, 113, 112, 114] * 5)
    low = pd.Series([95, 97, 96, 98, 100, 99, 101, 103, 102, 104] * 5)
    close = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109] * 5)
    
    k, d, j = calc.calculate_kdj(high, low, close)
    
    # KDJ应该是有效值
    assert not k.isna().all(), "K should not be all NaN"
    assert not d.isna().all(), "D should not be all NaN"
    assert not j.isna().all(), "J should not be all NaN"


def test_macd_calculation():
    """测试MACD计算"""
    calc = BacktestSignalCalculator()
    
    data = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109] * 5)
    
    macd_line, signal_line, macd_hist = calc.calculate_macd(data)
    
    # MACD应该是有效值
    assert not macd_line.isna().all(), "MACD line should not be all NaN"
    assert not signal_line.isna().all(), "Signal line should not be all NaN"
    assert not macd_hist.isna().all(), "MACD histogram should not be all NaN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
