"""
数据研究工具 - 用于探索历史市场数据，发现交易规律

功能：
1. 获取历史K线数据
2. 计算技术指标
3. 可视化分析
4. 统计分析和模式识别
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Optional
import json

from src.api.binance_client import BinanceClient
from src.data.processor import MarketDataProcessor
from src.config import Config


class DataExplorer:
    """历史数据探索工具"""
    
    def __init__(self):
        """初始化数据探索器"""
        self.config = Config()
        self.client = BinanceClient()
        self.processor = MarketDataProcessor()
        
        # 设置绘图风格
        sns.set_style("darkgrid")
        plt.rcParams['figure.figsize'] = (15, 10)
        
    def fetch_historical_data(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        days: int = 30
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            days: 历史天数
            
        Returns:
            原始K线数据DataFrame
        """
        print(f"\n{'='*60}")
        print(f"获取历史数据: {symbol} ({interval}), 最近 {days} 天")
        print(f"{'='*60}")
        
        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # 转换为毫秒时间戳
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        # 获取K线数据
        klines = self.client.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_ms,
            end_time=end_ms,
            limit=1000
        )
        
        if not klines:
            print(f"❌ 未获取到数据")
            return pd.DataFrame()
        
        # 转换为DataFrame
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # 数据类型转换
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        print(f"✅ 成功获取 {len(df)} 条K线数据")
        print(f"时间范围: {df['open_time'].min()} 到 {df['open_time'].max()}")
        print(f"\n数据预览:")
        print(df[['open_time', 'open', 'high', 'low', 'close', 'volume']].head())
        
        return df
    
    def analyze_data(self, df: pd.DataFrame) -> Dict:
        """
        分析数据统计特征
        
        Args:
            df: K线数据DataFrame
            
        Returns:
            统计分析结果
        """
        if df.empty:
            return {}
        
        print(f"\n{'='*60}")
        print("数据统计分析")
        print(f"{'='*60}")
        
        # 基础统计
        stats = {
            'count': len(df),
            'price_range': {
                'min': float(df['low'].min()),
                'max': float(df['high'].max()),
                'mean': float(df['close'].mean()),
                'std': float(df['close'].std())
            },
            'volume': {
                'total': float(df['volume'].sum()),
                'mean': float(df['volume'].mean()),
                'max': float(df['volume'].max())
            }
        }
        
        # 价格变化分析
        df['price_change'] = df['close'].pct_change() * 100
        df['price_range'] = ((df['high'] - df['low']) / df['low'] * 100)
        
        stats['volatility'] = {
            'mean_change': float(df['price_change'].mean()),
            'std_change': float(df['price_change'].std()),
            'max_rise': float(df['price_change'].max()),
            'max_fall': float(df['price_change'].min()),
            'mean_range': float(df['price_range'].mean())
        }
        
        # 趋势分析
        sma_20 = df['close'].rolling(window=20).mean()
        df['trend'] = df['close'] > sma_20
        
        bullish_count = df['trend'].sum()
        bearish_count = len(df) - bullish_count
        
        stats['trend'] = {
            'bullish_pct': float(bullish_count / len(df) * 100),
            'bearish_pct': float(bearish_count / len(df) * 100)
        }
        
        # 打印统计结果
        print(f"\n📊 基础统计:")
        print(f"  总K线数: {stats['count']}")
        print(f"  价格范围: {stats['price_range']['min']:.2f} - {stats['price_range']['max']:.2f}")
        print(f"  平均价格: {stats['price_range']['mean']:.2f} ± {stats['price_range']['std']:.2f}")
        
        print(f"\n📈 波动性分析:")
        print(f"  平均变化: {stats['volatility']['mean_change']:.3f}%")
        print(f"  波动标准差: {stats['volatility']['std_change']:.3f}%")
        print(f"  最大涨幅: {stats['volatility']['max_rise']:.2f}%")
        print(f"  最大跌幅: {stats['volatility']['max_fall']:.2f}%")
        print(f"  平均振幅: {stats['volatility']['mean_range']:.2f}%")
        
        print(f"\n📉 趋势分析:")
        print(f"  多头时段: {stats['trend']['bullish_pct']:.1f}%")
        print(f"  空头时段: {stats['trend']['bearish_pct']:.1f}%")
        
        return stats
    
    def visualize_data(self, df: pd.DataFrame, save_path: Optional[str] = None):
        """
        可视化数据分析
        
        Args:
            df: K线数据DataFrame
            save_path: 保存路径（可选）
        """
        if df.empty:
            return
        
        print(f"\n{'='*60}")
        print("生成可视化图表")
        print(f"{'='*60}")
        
        # 创建子图
        fig, axes = plt.subplots(4, 1, figsize=(15, 12))
        
        # 1. 价格走势
        axes[0].plot(df['open_time'], df['close'], label='Close Price', linewidth=1)
        sma_20 = df['close'].rolling(window=20).mean()
        sma_50 = df['close'].rolling(window=50).mean()
        axes[0].plot(df['open_time'], sma_20, label='SMA 20', alpha=0.7)
        axes[0].plot(df['open_time'], sma_50, label='SMA 50', alpha=0.7)
        axes[0].set_title('Price Trend with Moving Averages')
        axes[0].set_ylabel('Price (USDT)')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        
        # 2. 成交量
        axes[1].bar(df['open_time'], df['volume'], alpha=0.5, color='blue')
        axes[1].set_title('Trading Volume')
        axes[1].set_ylabel('Volume')
        axes[1].grid(True, alpha=0.3)
        
        # 3. 价格变化率
        df['price_change'] = df['close'].pct_change() * 100
        colors = ['green' if x > 0 else 'red' for x in df['price_change']]
        axes[2].bar(df['open_time'], df['price_change'], alpha=0.6, color=colors)
        axes[2].set_title('Price Change (%)')
        axes[2].set_ylabel('Change (%)')
        axes[2].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[2].grid(True, alpha=0.3)
        
        # 4. RSI指标
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        axes[3].plot(df['open_time'], rsi, label='RSI', color='purple', linewidth=1)
        axes[3].axhline(y=70, color='red', linestyle='--', alpha=0.5, label='Overbought (70)')
        axes[3].axhline(y=30, color='green', linestyle='--', alpha=0.5, label='Oversold (30)')
        axes[3].set_title('RSI Indicator')
        axes[3].set_ylabel('RSI')
        axes[3].set_xlabel('Time')
        axes[3].legend()
        axes[3].grid(True, alpha=0.3)
        axes[3].set_ylim(0, 100)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"✅ 图表已保存至: {save_path}")
        else:
            # 默认保存路径
            os.makedirs('research/outputs', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_path = f'research/outputs/data_analysis_{timestamp}.png'
            plt.savefig(default_path, dpi=300, bbox_inches='tight')
            print(f"✅ 图表已保存至: {default_path}")
        
        plt.close()
    
    def find_patterns(self, df: pd.DataFrame) -> Dict:
        """
        识别交易模式
        
        Args:
            df: K线数据DataFrame
            
        Returns:
            模式识别结果
        """
        if df.empty:
            return {}
        
        print(f"\n{'='*60}")
        print("模式识别分析")
        print(f"{'='*60}")
        
        patterns = {}
        
        # 1. 突破模式
        df['high_20'] = df['high'].rolling(window=20).max()
        df['low_20'] = df['low'].rolling(window=20).min()
        df['breakout_high'] = df['close'] > df['high_20'].shift(1)
        df['breakout_low'] = df['close'] < df['low_20'].shift(1)
        
        patterns['breakout'] = {
            'upward': int(df['breakout_high'].sum()),
            'downward': int(df['breakout_low'].sum())
        }
        
        # 2. 金叉死叉
        sma_10 = df['close'].rolling(window=10).mean()
        sma_30 = df['close'].rolling(window=30).mean()
        df['golden_cross'] = (sma_10 > sma_30) & (sma_10.shift(1) <= sma_30.shift(1))
        df['death_cross'] = (sma_10 < sma_30) & (sma_10.shift(1) >= sma_30.shift(1))
        
        patterns['ma_cross'] = {
            'golden': int(df['golden_cross'].sum()),
            'death': int(df['death_cross'].sum())
        }
        
        # 3. RSI超买超卖
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        df['rsi'] = rsi
        df['rsi_overbought'] = rsi > 70
        df['rsi_oversold'] = rsi < 30
        
        patterns['rsi'] = {
            'overbought': int(df['rsi_overbought'].sum()),
            'oversold': int(df['rsi_oversold'].sum())
        }
        
        # 4. 大幅波动
        df['price_change_pct'] = df['close'].pct_change() * 100
        df['large_up'] = df['price_change_pct'] > 3
        df['large_down'] = df['price_change_pct'] < -3
        
        patterns['volatility'] = {
            'large_up_moves': int(df['large_up'].sum()),
            'large_down_moves': int(df['large_down'].sum())
        }
        
        # 打印模式统计
        print(f"\n🔍 突破模式:")
        print(f"  向上突破: {patterns['breakout']['upward']} 次")
        print(f"  向下突破: {patterns['breakout']['downward']} 次")
        
        print(f"\n🔍 均线交叉:")
        print(f"  金叉: {patterns['ma_cross']['golden']} 次")
        print(f"  死叉: {patterns['ma_cross']['death']} 次")
        
        print(f"\n🔍 RSI信号:")
        print(f"  超买区: {patterns['rsi']['overbought']} 次")
        print(f"  超卖区: {patterns['rsi']['oversold']} 次")
        
        print(f"\n🔍 大幅波动:")
        print(f"  大涨(>3%): {patterns['volatility']['large_up_moves']} 次")
        print(f"  大跌(<-3%): {patterns['volatility']['large_down_moves']} 次")
        
        return patterns
    
    def generate_report(
        self,
        df: pd.DataFrame,
        stats: Dict,
        patterns: Dict,
        save_path: Optional[str] = None
    ):
        """
        生成研究报告
        
        Args:
            df: K线数据DataFrame
            stats: 统计分析结果
            patterns: 模式识别结果
            save_path: 保存路径（可选）
        """
        print(f"\n{'='*60}")
        print("生成研究报告")
        print(f"{'='*60}")
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'data_summary': {
                'total_bars': len(df),
                'time_range': {
                    'start': df['open_time'].min().isoformat(),
                    'end': df['open_time'].max().isoformat()
                }
            },
            'statistics': stats,
            'patterns': patterns,
            'recommendations': self._generate_recommendations(stats, patterns)
        }
        
        # 保存JSON报告
        if not save_path:
            os.makedirs('research/outputs', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_path = f'research/outputs/research_report_{timestamp}.json'
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 研究报告已保存至: {save_path}")
        
        # 打印建议
        print(f"\n📋 策略建议:")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"  {i}. {rec}")
    
    def _generate_recommendations(self, stats: Dict, patterns: Dict) -> List[str]:
        """生成交易策略建议"""
        recommendations = []
        
        # 基于波动性的建议
        if stats.get('volatility', {}).get('std_change', 0) > 2:
            recommendations.append("市场波动较大，建议使用突破策略或趋势跟随策略")
        else:
            recommendations.append("市场波动较小，建议使用均值回归策略")
        
        # 基于趋势的建议
        trend = stats.get('trend', {})
        if trend.get('bullish_pct', 0) > 60:
            recommendations.append("市场整体呈上升趋势，可考虑做多策略")
        elif trend.get('bearish_pct', 0) > 60:
            recommendations.append("市场整体呈下降趋势，可考虑做空策略或观望")
        else:
            recommendations.append("市场震荡，建议使用区间交易策略")
        
        # 基于RSI的建议
        rsi_patterns = patterns.get('rsi', {})
        if rsi_patterns.get('oversold', 0) > rsi_patterns.get('overbought', 0):
            recommendations.append("RSI超卖信号较多，可能存在反弹机会")
        elif rsi_patterns.get('overbought', 0) > rsi_patterns.get('oversold', 0):
            recommendations.append("RSI超买信号较多，注意回调风险")
        
        return recommendations


def main():
    """主函数 - 运行完整的数据探索流程"""
    print("\n" + "="*60)
    print("🔬 AI Trader - 数据研究工具")
    print("="*60)
    
    # 初始化探索器
    explorer = DataExplorer()
    
    # 1. 获取历史数据
    df = explorer.fetch_historical_data(
        symbol="BTCUSDT",
        interval="1h",
        days=30
    )
    
    if df.empty:
        print("❌ 数据获取失败，退出")
        return
    
    # 2. 统计分析
    stats = explorer.analyze_data(df)
    
    # 3. 模式识别
    patterns = explorer.find_patterns(df)
    
    # 4. 可视化
    explorer.visualize_data(df)
    
    # 5. 生成报告
    explorer.generate_report(df, stats, patterns)
    
    print(f"\n{'='*60}")
    print("✅ 数据研究完成!")
    print("="*60)


if __name__ == "__main__":
    main()
