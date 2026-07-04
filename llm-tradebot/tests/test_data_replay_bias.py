"""
测试数据回放器 Look-ahead Bias 修复
"""
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock
from src.backtest.data_replay import DataReplayAgent, MarketSnapshot

def test_get_current_price_uses_open():
    """验证 get_current_price 使用 Open 价格"""
    replay = DataReplayAgent("BTCUSDT", "2024-01-01", "2024-01-02")
    
    # 模拟快照
    mock_snapshot = MagicMock(spec=MarketSnapshot)
    # 设置 live_5m 为字典，包含 open 和 close
    mock_snapshot.live_5m = {
        'open': 50000.0,
        'high': 51000.0,
        'low': 49000.0,
        'close': 50500.0  # 收盘价不同于开盘价
    }
    
    replay.latest_snapshot = mock_snapshot
    
    price = replay.get_current_price()
    
    # 应该等于 Open (50000)，而不是 Close (50500)
    assert price == 50000.0, f"Price {price} should be Open price 50000.0"
    assert price != 50500.0, "Price should not be Close price (Limit Look-ahead Bias)"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
