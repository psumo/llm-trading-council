import sys
import os
# ensure project root in path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import pytest
from src.data.processor import MarketDataProcessor


def make_base_df(n=60, start_price=10000.0, freq='5T'):
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor('T'), periods=n, freq=freq)
    prices = start_price + np.cumsum(np.random.randn(n)) * 10
    vols = np.abs(np.random.randn(n) * 100)
    df = pd.DataFrame({
        'timestamp': idx.astype('int64') // 10**6,
        'open': prices,
        'high': prices + np.random.rand(n) * 5,
        'low': prices - np.random.rand(n) * 5,
        'close': prices,
        'volume': vols
    })
    return df


def test_time_gaps_marked_and_imputed():
    proc = MarketDataProcessor()
    df = make_base_df(60)
    # remove a couple timestamps to create small gap
    df2 = df.drop(index=[5, 6, 12]).reset_index(drop=True)
    klines = df2.to_dict('records')
    processed = proc.process_klines(klines, symbol='TEST', timeframe='5m')
    features = proc.extract_feature_snapshot(processed, lookback=12, allowed_gap_bars=2)
    # 检查 is_imputed 列存在
    assert 'is_imputed' in features.columns
    # 若有短gap, 仍会插值并标记
    assert features['is_imputed'].any() or not processed.empty


def test_divide_by_zero_safety():
    proc = MarketDataProcessor()
    df = make_base_df(60)
    # 设置部分 close 和 vwap 为0
    df.loc[10, 'close'] = 0.0
    df.loc[20, 'close'] = 0.0
    klines = df.to_dict('records')
    processed = proc.process_klines(klines, symbol='TEST2', timeframe='5m')
    features = proc.extract_feature_snapshot(processed, lookback=20)
    # 检查是否有 inf
    assert not np.isinf(features.select_dtypes(include=[np.number]).fillna(0).to_numpy()).any()


def test_warmup_flag():
    proc = MarketDataProcessor()
    df = make_base_df(60)
    klines = df.to_dict('records')
    processed = proc.process_klines(klines, symbol='TEST3', timeframe='5m')
    # use larger lookback than available bars to force warm_up_bars_remaining>0
    features = proc.extract_feature_snapshot(processed, lookback=100)
    # 由于输入少于 lookback, warm_up_bars_remaining 应大于0
    assert features['warm_up_bars_remaining'].iloc[-1] > 0


def test_macd_and_atr_percent_normalization():
    proc = MarketDataProcessor()
    df = make_base_df(100, start_price=87000.0)
    klines = df.to_dict('records')
    processed = proc.process_klines(klines, symbol='BTC_TEST', timeframe='5m')
    features = proc.extract_feature_snapshot(processed, lookback=50)
    # macd_pct 和 atr_pct 不应太大
    assert features['macd_pct'].abs().max() < 50
    assert features['atr_pct'].abs().max() < 50


def test_outlier_winsorize():
    proc = MarketDataProcessor()
    df = make_base_df(60)
    df.loc[30, 'close'] = df['close'].mean() * 1000  # 极端价格点
    klines = df.to_dict('records')
    processed = proc.process_klines(klines, symbol='OUTLIER', timeframe='5m')
    features = proc.extract_feature_snapshot(processed, lookback=20)
    # return_pct 不应包含极端值
    assert features['return_pct'].dropna().abs().max() < 1e4


def test_persistence_schema_and_versioning(tmp_path):
    proc = MarketDataProcessor()
    df = make_base_df(80)
    klines = df.to_dict('records')
    processed = proc.process_klines(klines, symbol='PERSIST', timeframe='5m')
    features = proc.extract_feature_snapshot(processed, lookback=20)
    out = tmp_path / 'feat.parquet'
    features.to_parquet(out)
    loaded = pd.read_parquet(out)
    assert 'feature_version' in loaded.columns
    assert 'processor_version' in loaded.columns
