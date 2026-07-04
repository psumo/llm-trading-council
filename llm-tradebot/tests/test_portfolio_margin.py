"""
测试投资组合保证金逻辑
"""
import pytest
from datetime import datetime
from src.backtest.portfolio import BacktestPortfolio, Side, MarginConfig

def test_margin_deduction():
    """测试开仓时是否正确扣除保证金而非全额"""
    # 初始资金 10000, 10x 杠杆, 无滑点
    portfolio = BacktestPortfolio(
        initial_capital=10000.0,
        slippage=0.0,
        margin_config=MarginConfig(leverage=10)
    )
    
    # 开仓 1 BTC @ 50000 USD
    # 名义价值 = 50000
    # 应扣除保证金 = 5000
    # 手续费 (Maker 0.02%) = 10 (假设在这里忽略或很小)
    
    trade = portfolio.open_position(
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        price=50000.0,
        timestamp=datetime.now()
    )
    
    assert trade is not None
    
    # 验证现金余额
    # 期望余额 = 10000 - 5000 (Margin) - 手续费
    # 手续费 approx 50000 * 0.0004 (Taker default) = 20
    # 所以余额应约为 4980
    
    expected_margin = 5000.0
    expected_fee = 50000.0 * 0.0004
    expected_cash = 10000.0 - expected_margin - expected_fee
    
    assert abs(portfolio.cash - expected_cash) < 1.0, f"Cash ${portfolio.cash} != Expected ${expected_cash}"

def test_margin_return():
    """测试平仓时是否归还保证金"""
    portfolio = BacktestPortfolio(
        initial_capital=10000.0,
        slippage=0.0,
        margin_config=MarginConfig(leverage=10)
    )
    
    # 开仓
    portfolio.open_position(
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        price=50000.0,
        timestamp=datetime.now()
    )
    
    initial_cash_after_open = portfolio.cash
    
    # 平仓 @ 51000 (盈利 1000)
    portfolio.close_position(
        symbol="BTCUSDT",
        price=51000.0,
        timestamp=datetime.now()
    )
    
    # 期望余额 = 开仓后余额 + 保证金(5000) + 盈利(1000) - 平仓手续费
    # 平仓手续费 = 51000 * 0.0004 = 20.4
    
    expected_return = 5000.0 + 1000.0 - (51000.0 * 0.0004)
    expected_final_cash = initial_cash_after_open + expected_return
    
    assert abs(portfolio.cash - expected_final_cash) < 1.0, f"Final Cash ${portfolio.cash} != Expected ${expected_final_cash}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
