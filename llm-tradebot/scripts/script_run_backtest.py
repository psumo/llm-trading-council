
import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import BacktestEngine, BacktestConfig

async def run_backtest():
    print("🚀 Starting Optimized Backtest for LINKUSDT (Foundations Config)...")
    
    # Robust Config based on previous success
    # Start: 16:00 (Skip warmup)
    # End: Day string (Ensure data fetch/cache hit)
    
    config = BacktestConfig(
        symbol="LINKUSDT",
        start_date="2026-01-01 16:00", 
        end_date="2026-01-02", # Implies 2026-01-03 00:00 in DataReplay, covers full range
        initial_capital=10000.0,
        step=1, 
        use_llm=True, 
        slippage=0.001,
        commission=0.0004,
        strategy_mode="agent"
    )
    
    engine = BacktestEngine(config)
    
    # 2. Run Backtest
    print(f"⚙️ Config: {config.symbol} {config.start_date} -> {config.end_date}")
    t0 = datetime.now()
    
    try:
        report = await engine.run()
        duration = (datetime.now() - t0).total_seconds()
        
        print(f"\n✅ Backtest Completed in {duration:.2f}s")
        print("="*40)
        print(f"Total Trades: {report.metrics.total_trades}")
        print(f"Win Rate: {report.metrics.win_rate:.1f}%")
        print(f"Total Return: {report.metrics.total_return:.2f}%")
        print(f"Max Drawdown: {report.metrics.max_drawdown_pct:.2f}%")
        print(f"Final Equity: ${report.metrics.final_equity:.2f}")
        print("="*40)
        
        # 3. Save JSON for frontend
        import json
        output_file = f"data/backtest/backtest_{int(datetime.now().timestamp())}_LINKUSDT_final.json"
        
        # Ensure directory
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
            
        print(f"📁 Report saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Backtest Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_backtest())
