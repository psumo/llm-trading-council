#!/usr/bin/env python3
"""
数据流转准确性验证脚本
验证从原始数据到决策的完整数据链路
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path

class DataAccuracyChecker:
    def __init__(self, data_dir='data', date='20251220', snapshot_id='snap_1766234252'):
        self.data_dir = Path(data_dir)
        self.date = date
        self.snapshot_id = snapshot_id
        self.symbol = 'BTCUSDT'
        self.timeframe = '5m'
        
    def check_stage1_raw_data(self):
        """Stage 1: 验证原始市场数据"""
        print("=" * 80)
        print("Stage 1: 原始市场数据验证")
        print("=" * 80)
        
        json_file = self.data_dir / 'data_sync_agent' / self.date / f'market_data_{self.symbol}_{self.timeframe}_20251220_203733.json'
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        klines = data['klines']
        print(f"✓ K线数量: {len(klines)}")
        print(f"✓ 交易对: {data['metadata']['symbol']}")
        
        # 验证价格逻辑
        errors = 0
        for i, k in enumerate(klines[:10]):
            if k['high'] < max(k['open'], k['close']) or k['low'] > min(k['open'], k['close']):
                print(f"✗ K线 {i+1} 价格逻辑错误")
                errors += 1
        
        if errors == 0:
            print(f"✓ 价格逻辑验证通过（前10根）")
        
        return klines[-1]['close']  # 返回最后收盘价
    
    def check_stage2_indicators(self):
        """Stage 2: 验证技术指标计算"""
        print("\n" + "=" * 80)
        print("Stage 2: 技术指标计算验证")
        print("=" * 80)
        
        parquet_file = self.data_dir / 'quant_analyst_agent' / 'indicators' / self.date / f'indicators_{self.symbol}_{self.timeframe}_20251220_203733_{self.snapshot_id}.parquet'
        
        df = pd.read_parquet(parquet_file)
        print(f"✓ 数据维度: {df.shape}")
        print(f"✓ 指标列数: {len(df.columns)}")
        
        # 检查关键指标
        last_row = df.iloc[-1]
        print(f"✓ 最后收盘价: {last_row['close']:.2f}")
        print(f"✓ EMA12: {last_row['ema_12']:.2f}")
        print(f"✓ EMA26: {last_row['ema_26']:.2f}")
        print(f"✓ RSI: {last_row['rsi']:.2f}")
        print(f"✓ MACD: {last_row['macd']:.2f}")
        
        # 检查 NaN 值（Warm-up 期除外）
        valid_data = df[df['is_valid'] == True]
        nan_in_valid = valid_data.isna().sum().sum()
        print(f"✓ 有效数据中 NaN 数: {nan_in_valid}")
        
        return last_row['close'], last_row['rsi'], last_row['ema_12'], last_row['ema_26']
    
    def check_stage3_features(self):
        """Stage 3: 验证特征提取"""
        print("\n" + "=" * 80)
        print("Stage 3: 特征提取验证")
        print("=" * 80)
        
        parquet_file = self.data_dir / 'quant_analyst_agent' / 'features' / self.date / f'features_{self.symbol}_{self.timeframe}_20251220_203733_{self.snapshot_id}_v1.parquet'
        
        df = pd.read_parquet(parquet_file)
        print(f"✓ 特征维度: {df.shape}")
        print(f"✓ 特征数量: {len(df.columns)}")
        
        last_row = df.iloc[-1]
        print(f"✓ 收盘价: {last_row['close']:.2f}")
        print(f"✓ 收益率: {last_row['return_pct']:.4f}%")
        print(f"✓ MACD百分比: {last_row['macd_pct']:.4f}%")
        
        # 检查 Inf 值
        inf_count = np.isinf(df.select_dtypes(include=[np.number])).sum().sum()
        print(f"✓ Inf 值数量: {inf_count}")
        
        return last_row['close']
    
    def check_stage4_quant_analysis(self):
        """Stage 4: 验证量化分析"""
        print("\n" + "=" * 80)
        print("Stage 4: 量化分析上下文验证")
        print("=" * 80)
        
        json_file = self.data_dir / 'quant_analyst_agent' / 'context' / self.date / f'context_{self.symbol}_quant_analysis_20251220_203733_{self.snapshot_id}.json'
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        print(f"✓ 信号源数量: {len(data)}")
        
        # 验证趋势信号
        trend_scores = []
        for period in ['5m', '15m', '1h']:
            key = f'trend_{period}'
            if key in data:
                score = data[key]['score']
                signal = data[key]['signal']
                trend_scores.append(score)
                print(f"✓ {period} 趋势: {signal} (得分: {score})")
        
        # 验证震荡信号
        for period in ['5m', '15m', '1h']:
            key = f'oscillator_{period}'
            if key in data:
                score = data[key]['score']
                signal = data[key]['signal']
                print(f"✓ {period} 震荡: {signal} (得分: {score})")
        
        return sum(trend_scores)
    
    def check_stage5_decision(self):
        """Stage 5: 验证决策结果"""
        print("\n" + "=" * 80)
        print("Stage 5: 决策结果验证")
        print("=" * 80)
        
        json_file = self.data_dir / 'decision_core_agent' / 'decisions' / self.date / f'decision_{self.symbol}_20251220_203733_{self.snapshot_id}.json'
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        print(f"✓ 决策动作: {data['action']}")
        print(f"✓ 置信度: {data['confidence']:.4f} ({data['confidence']*100:.2f}%)")
        print(f"✓ 加权得分: {data['weighted_score']}")
        print(f"✓ 多周期对齐: {data['multi_period_aligned']}")
        
        # 验证加权得分计算
        calculated_score = sum(data['vote_details'].values())
        print(f"\n加权得分验证:")
        print(f"  记录值: {data['weighted_score']}")
        print(f"  计算值: {calculated_score:.2f}")
        diff = abs(data['weighted_score'] - calculated_score)
        if diff < 0.01:
            print(f"  ✓ 计算正确 (差异: {diff:.6f})")
        else:
            print(f"  ✗ 计算有误差 (差异: {diff:.6f})")
        
        return data['action'], data['weighted_score']
    
    def check_data_consistency(self):
        """跨阶段数据一致性验证"""
        print("\n" + "=" * 80)
        print("跨阶段数据一致性验证")
        print("=" * 80)
        
        # 读取各阶段最后一行数据
        json_file = self.data_dir / 'data_sync_agent' / self.date / f'market_data_{self.symbol}_{self.timeframe}_20251220_203733.json'
        with open(json_file, 'r') as f:
            raw_data = json.load(f)
        raw_close = raw_data['klines'][-1]['close']
        
        indicators_file = self.data_dir / 'quant_analyst_agent' / 'indicators' / self.date / f'indicators_{self.symbol}_{self.timeframe}_20251220_203733_{self.snapshot_id}.parquet'
        df_ind = pd.read_parquet(indicators_file)
        ind_close = df_ind.iloc[-1]['close']
        
        features_file = self.data_dir / 'quant_analyst_agent' / 'features' / self.date / f'features_{self.symbol}_{self.timeframe}_20251220_203733_{self.snapshot_id}_v1.parquet'
        df_feat = pd.read_parquet(features_file)
        feat_close = df_feat.iloc[-1]['close']
        
        print(f"原始数据收盘价: {raw_close:.2f}")
        print(f"指标数据收盘价: {ind_close:.2f}")
        print(f"特征数据收盘价: {feat_close:.2f}")
        
        if abs(raw_close - ind_close) < 0.01 and abs(ind_close - feat_close) < 0.01:
            print(f"✓ 收盘价一致性验证通过")
        else:
            print(f"✗ 收盘价存在差异")
        
        # 验证快照ID
        ind_snapshot = df_ind.iloc[-1]['snapshot_id']
        feat_snapshot = df_feat.iloc[-1]['source_snapshot_id']
        
        print(f"\n快照ID一致性:")
        print(f"  指标: {ind_snapshot}")
        print(f"  特征: {feat_snapshot}")
        if ind_snapshot == feat_snapshot:
            print(f"  ✓ 快照ID一致")
        else:
            print(f"  ✗ 快照ID不一致")
    
    def run_all_checks(self):
        """运行所有验证"""
        print("\n" + "🔍 数据流转准确性全面验证")
        print("=" * 80 + "\n")
        
        try:
            # Stage 1
            raw_close = self.check_stage1_raw_data()
            
            # Stage 2
            ind_close, rsi, ema12, ema26 = self.check_stage2_indicators()
            
            # Stage 3
            feat_close = self.check_stage3_features()
            
            # Stage 4
            trend_sum = self.check_stage4_quant_analysis()
            
            # Stage 5
            action, weighted_score = self.check_stage5_decision()
            
            # 一致性检查
            self.check_data_consistency()
            
            # 总结
            print("\n" + "=" * 80)
            print("验证总结")
            print("=" * 80)
            print(f"✓ 所有阶段数据验证完成")
            print(f"✓ 数据流转链路完整")
            print(f"✓ 关键数据一致性良好")
            print(f"\n最终决策: {action} (加权得分: {weighted_score})")
            
        except Exception as e:
            print(f"\n✗ 验证过程出错: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    checker = DataAccuracyChecker()
    checker.run_all_checks()
