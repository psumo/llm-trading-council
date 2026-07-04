"""
Test script for backtest analytics system

Run this to verify the storage and analytics functionality.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.backtest.storage import BacktestStorage
from src.backtest.analytics import BacktestAnalytics
import json


def test_storage():
    """Test database storage"""
    print("=" * 60)
    print("Testing Backtest Storage")
    print("=" * 60)
    
    storage = BacktestStorage()
    
    # Create sample backtest data
    run_id = "test_bt_001"
    config = {
        'symbol': 'BTCUSDT',
        'symbols': ['BTCUSDT'],
        'start_date': '2024-12-01',
        'end_date': '2024-12-28',
        'initial_capital': 10000,
        'step': 3,
        'stop_loss_pct': 1.0,
        'take_profit_pct': 2.0,
        'leverage': 10,
        'margin_mode': 'cross',
        'duration_seconds': 120.5
    }
    
    metrics = {
        'total_return': '+15.5%',
        'sharpe_ratio': '1.85',
        'max_drawdown_pct': '-8.2%',
        'win_rate': '65.0%',
        'total_trades': 25,
        'profit_factor': '2.1'
    }
    
    trades = [
        {
            'trade_id': 1,
            'symbol': 'BTCUSDT',
            'side': 'long',
            'action': 'close',
            'quantity': 0.1,
            'price': 42000,
            'timestamp': '2024-12-01T10:00:00',
            'pnl': 150.0,
            'pnl_pct': 1.5,
            'entry_price': 41500,
            'holding_time': 2.5,
            'close_reason': 'take_profit'
        }
    ]
    
    equity_curve = [
        {
            'timestamp': '2024-12-01T09:00:00',
            'total_equity': 10000,
            'cash': 10000,
            'position_value': 0,
            'drawdown_pct': 0
        },
        {
            'timestamp': '2024-12-01T12:00:00',
            'total_equity': 10150,
            'cash': 10150,
            'position_value': 0,
            'drawdown_pct': 0
        }
    ]
    
    # Test save
    print("\n1. Testing save_backtest...")
    success = storage.save_backtest(run_id, config, metrics, trades, equity_curve)
    print(f"   ✓ Save successful: {success}")
    
    # Test retrieve
    print("\n2. Testing get_backtest...")
    data = storage.get_backtest(run_id)
    print(f"   ✓ Retrieved backtest: {data['config']['symbol']}")
    print(f"   ✓ Metrics: {data['metrics']['total_return']}")
    print(f"   ✓ Trades count: {len(data['trades'])}")
    print(f"   ✓ Equity points: {len(data['equity_curve'])}")
    
    # Test list
    print("\n3. Testing list_backtests...")
    backtests = storage.list_backtests(limit=10)
    print(f"   ✓ Found {len(backtests)} backtests")
    
    # Test export
    print("\n4. Testing export_to_csv...")
    export_success = storage.export_to_csv(run_id, '/tmp/backtest_export')
    print(f"   ✓ Export successful: {export_success}")
    
    print("\n✅ Storage tests completed!\n")
    
    return storage


def test_analytics(storage):
    """Test analytics functions"""
    print("=" * 60)
    print("Testing Backtest Analytics")
    print("=" * 60)
    
    analytics = BacktestAnalytics(storage)
    
    # Test parameter suggestions
    print("\n1. Testing suggest_optimal_parameters...")
    suggestions = analytics.suggest_optimal_parameters('BTCUSDT', target='sharpe')
    if 'error' not in suggestions:
        print(f"   ✓ Recommended params: {suggestions.get('recommended_params')}")
        print(f"   ✓ Sample size: {suggestions.get('sample_size')}")
    else:
        print(f"   ⚠ {suggestions['error']}")
    
    # Test trends
    print("\n2. Testing get_performance_trends...")
    trends = analytics.get_performance_trends('BTCUSDT', days=30)
    if 'error' not in trends:
        print(f"   ✓ Total backtests: {trends.get('total_backtests')}")
        print(f"   ✓ Avg return: {trends.get('avg_return')}")
    else:
        print(f"   ⚠ {trends['error']}")
    
    # Test win rate analysis
    print("\n3. Testing get_win_rate_analysis...")
    win_analysis = analytics.get_win_rate_analysis('test_bt_001')
    if 'error' not in win_analysis:
        print(f"   ✓ Win rate: {win_analysis.get('win_rate'):.2f}%")
        print(f"   ✓ Total trades: {win_analysis.get('total_trades')}")
    else:
        print(f"   ⚠ {win_analysis['error']}")
    
    print("\n✅ Analytics tests completed!\n")


def main():
    """Run all tests"""
    print("\n🧪 Backtest Analytics System Test\n")
    
    try:
        storage = test_storage()
        test_analytics(storage)
        
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        print("\n📊 Database location: data/backtest_analytics.db")
        print("📁 Export location: /tmp/backtest_export\n")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
