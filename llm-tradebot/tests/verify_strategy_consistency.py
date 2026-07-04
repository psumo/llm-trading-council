
import sys
import os
import asyncio
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.agent_wrapper import BacktestAgentRunner
from src.agents.data_sync_agent import MarketSnapshot

def create_mock_df(periods=100, start_price=100.0):
    """Create a mock DataFrame with enough data for analysis"""
    data = []
    price = start_price
    for i in range(periods):
        price += (i % 2 - 0.5) * 2 # Random walkish
        data.append({
            'timestamp': datetime.now(),
            'open': price,
            'high': price + 1,
            'low': price - 1,
            'close': price + 0.5,
            'volume': 1000
        })
    df = pd.DataFrame(data)
    # Add indicators needed by StrategyComposer
    df['ema_20'] = df['close'].ewm(span=20).mean()
    df['ema_60'] = df['close'].ewm(span=60).mean()
    df['bb_upper'] = df['close'] * 1.02
    df['bb_middle'] = df['close']
    df['bb_lower'] = df['close'] * 0.98
    df['kdj_k'] = 50
    df['kdj_j'] = 50
    return df

async def verify_strategy():
    print("🧪 Verifying Strategy Integration...")
    
    # 1. Initialize Runner with LLM enabled
    config = {'use_llm': True, 'symbol': 'BTCUSDT'}
    runner = BacktestAgentRunner(config)
    
    # Mock StrategyEngine.make_decision to avoid API cost and verify context
    original_make_decision = runner.llm_engine.make_decision
    
    captured_context = []
    
    def mock_make_decision(market_context_text, market_context_data, reflection=None):
        print("\n📝 CAPTURED CONTEXT START")
        print(market_context_text[:500] + "...")
        print("📝 CAPTURED CONTEXT END\n")
        captured_context.append(market_context_text)
        return {
            'action': 'hold',
            'confidence': 50,
            'reasoning': 'Mock Decision',
            'weighted_score': 0
        }
        
    runner.llm_engine.make_decision = mock_make_decision
    
    # 2. Create Mock Snapshot
    df_1h = create_mock_df(100)
    df_15m = create_mock_df(100)
    df_5m = create_mock_df(100)
    
    snapshot = MarketSnapshot(
        timestamp=datetime.now(),
        live_5m={'close': 105.0},
        live_15m={},
        live_1h={},
        raw_1h=[], raw_15m=[], raw_5m=[],
        stable_1h=df_1h,
        stable_15m=df_15m,
        stable_5m=df_5m,
        alignment_ok=True,
        fetch_duration=0.0
    )
    
    # 3. Run Step
    print("🏃 Running Step...")
    result = await runner.step(snapshot)
    
    print("\n✅ Result:", result)
    
    # 4. Verify Context Content
    if captured_context:
        ctx = captured_context[0]
        checks = [
            "Four-Layer Strategy Status",
            "Detailed Market Analysis",
            "Trend & Direction Analysis",
            "Entry Zone Analysis"
        ]
        all_passed = True
        for check in checks:
            if check in ctx:
                print(f"✅ Found '{check}'")
            else:
                print(f"❌ Missing '{check}'")
                all_passed = False
                
        if all_passed:
            print("\n🎉 VERIFICATION SUCCESS: Context contains all required multi-agent sections!")
        else:
            print("\n⚠️ VERIFICATION FAILED: Missing sections in context.")
    else:
        print("\n❌ VERIFICATION FAILED: No context captured (LLM not called?)")

if __name__ == "__main__":
    asyncio.run(verify_strategy())
