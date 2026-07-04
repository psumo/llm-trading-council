"""
测试回测配置验证功能
"""
import pytest
from src.backtest.engine import BacktestConfig


def test_valid_config():
    """测试有效配置"""
    config = BacktestConfig(
        symbol="BTCUSDT",
        start_date="2024-01-01",
        end_date="2024-12-31",
        initial_capital=10000,
        leverage=5
    )
    assert config.symbol == "BTCUSDT"
    assert config.leverage == 5


def test_invalid_date_format():
    """测试无效日期格式"""
    with pytest.raises(ValueError, match="Invalid date format"):
        BacktestConfig(
            symbol="BTCUSDT",
            start_date="2024/01/01",  # 错误格式
            end_date="2024-12-31"
        )


def test_start_after_end():
    """测试开始日期晚于结束日期"""
    with pytest.raises(ValueError, match="must be before"):
        BacktestConfig(
            symbol="BTCUSDT",
            start_date="2024-12-31",
            end_date="2024-01-01"
        )


def test_negative_capital():
    """测试负数初始资金"""
    with pytest.raises(ValueError, match="initial_capital must be positive"):
        BacktestConfig(
            symbol="BTCUSDT",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_capital=-1000
        )


def test_invalid_leverage():
    """测试无效杠杆"""
    with pytest.raises(ValueError, match="leverage must be between"):
        BacktestConfig(
            symbol="BTCUSDT",
            start_date="2024-01-01",
            end_date="2024-12-31",
            leverage=200  # 超出范围
        )


def test_invalid_stop_loss():
    """测试无效止损百分比"""
    with pytest.raises(ValueError, match="stop_loss_pct must be between"):
        BacktestConfig(
            symbol="BTCUSDT",
            start_date="2024-01-01",
            end_date="2024-12-31",
            stop_loss_pct=150  # 超出范围
        )


def test_invalid_strategy_mode():
    """测试无效策略模式"""
    with pytest.raises(ValueError, match="strategy_mode must be"):
        BacktestConfig(
            symbol="BTCUSDT",
            start_date="2024-01-01",
            end_date="2024-12-31",
            strategy_mode="invalid_mode"
        )


def test_empty_symbol():
    """测试空交易对"""
    with pytest.raises(ValueError, match="symbol must be a non-empty string"):
        BacktestConfig(
            symbol="",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )


def test_no_duplicate_fields():
    """验证没有重复字段定义"""
    import inspect
    from dataclasses import fields
    
    config_fields = fields(BacktestConfig)
    field_names = [f.name for f in config_fields]
    
    # 检查use_llm和llm_cache只出现一次
    assert field_names.count('use_llm') == 1, "use_llm should appear only once"
    assert field_names.count('llm_cache') == 1, "llm_cache should appear only once"
    
    # 检查没有重复字段
    assert len(field_names) == len(set(field_names)), "No duplicate field names allowed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
