"""策略回测框架"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict
import json

from src.api.binance_client import BinanceClient
from src.data.processor import MarketDataProcessor
from src.features.builder import FeatureBuilder
from src.config import Config


class Backtester:
    def __init__(self):
        self.config = Config()
        self.client = BinanceClient()
        self.processor = MarketDataProcessor()
        self.feature_builder = FeatureBuilder(self.config)
        self.trades = []
        self.equity_curve = []
    
    def run_backtest(self, strategy_func, symbol="BTCUSDT", interval="1h", 
                     days=30, initial_capital=10000.0, position_size=0.1):
        print(f"\n{'='*60}")
        print(f"🔄 开始回测: {symbol} ({interval}), {days} 天")
        print(f"{'='*60}")
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        klines = self.client.get_klines(symbol, interval, start_ms, end_ms, 1000)
        
        if not klines:
            return {}
        
        print(f"✅ 获取到 {len(klines)} 条K线")
        
        capital = initial_capital
        position = 0.0
        position_price = 0.0
        self.trades = []
        
        for i, kline in enumerate(klines):
            if i < 50:
                continue
            
            processed_df = self.processor.process_klines(klines[:i+1])
            if processed_df is None:
                continue
                
            market_state = self.feature_builder.build_features(processed_df, None)
            current_price = float(kline[4])
            current_time = pd.to_datetime(kline[0], unit='ms')
            
            signal = strategy_func(market_state)
            
            if signal == 'BUY' and position == 0:
                position_value = capital * position_size
                position = position_value / current_price
                position_price = current_price
                capital -= position_value
                self.trades.append({'time': current_time, 'type': 'BUY', 'price': current_price})
                print(f"[{current_time}] 🟢 买入 @ ${current_price:.2f}")
                
            elif signal == 'SELL' and position > 0:
                position_value = position * current_price
                profit = position_value - (position * position_price)
                profit_pct = (current_price / position_price - 1) * 100
                capital += position_value
                self.trades.append({'time': current_time, 'type': 'SELL', 'price': current_price, 'profit': profit})
                print(f"[{current_time}] 🔴 卖出 @ ${current_price:.2f} | 盈亏: ${profit:.2f} ({profit_pct:+.2f}%)")
                position = 0
        
        if position > 0:
            final_price = float(klines[-1][4])
            profit = (position * final_price) - (position * position_price)
            capital += position * final_price
            self.trades.append({'time': pd.to_datetime(klines[-1][0], unit='ms'), 'type': 'SELL', 'price': final_price, 'profit': profit})
        
        return self._calculate_metrics(initial_capital, capital)
    
    def _calculate_metrics(self, initial, final):
        return {
            'initial_capital': initial,
            'final_capital': final,
            'total_return': final - initial,
            'total_return_pct': (final / initial - 1) * 100,
            'total_trades': len([t for t in self.trades if t['type'] == 'BUY']),
            'trades': self.trades
        }
    
    def save_results(self, results, save_path=None):
        if not save_path:
            os.makedirs('research/outputs', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_path = f'research/outputs/backtest_{timestamp}.json'
        results_copy = {**results, 'trades': [{**t, 'time': t['time'].isoformat()} for t in results['trades']]}
        with open(save_path, 'w') as f:
            json.dump(results_copy, f, indent=2)
        print(f"✅ 保存至: {save_path}")


def simple_ma_crossover_strategy(market_state):
    indicators = market_state.get('indicators', {})
    sma_20 = indicators.get('sma_20')
    sma_50 = indicators.get('sma_50')
    price = market_state.get('current_price')
    
    if sma_20 and sma_50 and price:
        if sma_20 > sma_50 and price > sma_20:
            return 'BUY'
        elif sma_20 < sma_50:
            return 'SELL'
    return 'HOLD'


if __name__ == "__main__":
    backtester = Backtester()
    results = backtester.run_backtest(simple_ma_crossover_strategy, days=7)
    backtester.save_results(results)
