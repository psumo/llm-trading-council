"""
📦 K-line Data Cache Manager
============================

Provides incremental parquet-based caching for K-line data to reduce API calls.

Features:
- Local parquet storage per symbol/interval
- Incremental fetch (only new data since last cache)
- Automatic cache cleanup (keeps last 30 days)
- Thread-safe operations

Author: AI Trader Team
Date: 2026-01-10
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import threading

from src.utils.logger import log


class KlineCache:
    """
    K-line data cache with parquet storage
    
    Storage structure:
    data/kline_cache/
    ├── BTCUSDT/
    │   ├── 5m.parquet
    │   ├── 15m.parquet
    │   └── 1h.parquet
    └── ETHUSDT/
        └── ...
    """
    
    # Default retention period (days)
    DEFAULT_RETENTION_DAYS = 30
    
    # Interval to milliseconds mapping
    INTERVAL_MS = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
    }
    
    def __init__(self, cache_dir: str = "data/kline"):
        """
        Initialize K-line cache
        
        Args:
            cache_dir: Directory for parquet cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        log.info(f"📦 KlineCache initialized | Dir: {self.cache_dir}")
    
    def _get_cache_path(self, symbol: str, interval: str) -> Path:
        """Get cache file path for symbol/interval"""
        symbol_dir = self.cache_dir / symbol.upper()
        symbol_dir.mkdir(parents=True, exist_ok=True)
        return symbol_dir / f"{interval}.parquet"
    
    def get_cached_data(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """
        Get cached data for symbol/interval
        
        Returns:
            DataFrame with cached K-lines or None if no cache
        """
        cache_path = self._get_cache_path(symbol, interval)
        
        if not cache_path.exists():
            return None
        
        try:
            with self._lock:
                df = pd.read_parquet(cache_path)
                log.debug(f"📦 Cache loaded: {symbol}/{interval} ({len(df)} rows)")
                return df
        except Exception as e:
            log.warning(f"⚠️ Failed to read cache {cache_path}: {e}")
            return None
    
    def get_last_timestamp(self, symbol: str, interval: str) -> Optional[int]:
        """
        Get the last cached timestamp (milliseconds)
        
        Returns:
            Last timestamp in ms or None if no cache
        """
        df = self.get_cached_data(symbol, interval)
        
        if df is None or df.empty:
            return None
        
        # Assume 'timestamp' column exists
        if 'timestamp' in df.columns:
            return int(df['timestamp'].max())
        elif df.index.name == 'timestamp':
            return int(df.index.max())
        
        return None
    
    def append_data(
        self,
        symbol: str,
        interval: str,
        new_data: List[Dict],
        retention_days: int = DEFAULT_RETENTION_DAYS
    ) -> pd.DataFrame:
        """
        Append new K-line data to cache
        
        Args:
            symbol: Trading pair
            interval: Timeframe (5m, 15m, 1h)
            new_data: List of new K-line dicts
            retention_days: Days to keep in cache
            
        Returns:
            Combined DataFrame (cached + new)
        """
        if not new_data:
            cached = self.get_cached_data(symbol, interval)
            return cached if cached is not None else pd.DataFrame()
        
        # Convert new data to DataFrame
        new_df = pd.DataFrame(new_data)
        
        # Ensure timestamp is int64
        if 'timestamp' in new_df.columns:
            new_df['timestamp'] = new_df['timestamp'].astype('int64')
        
        # Load existing cache
        cached_df = self.get_cached_data(symbol, interval)
        
        if cached_df is not None and not cached_df.empty:
            # Reset index if timestamp is index
            if cached_df.index.name == 'timestamp':
                cached_df = cached_df.reset_index()
            
            # Combine and deduplicate
            combined = pd.concat([cached_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
            combined = combined.sort_values('timestamp').reset_index(drop=True)
        else:
            combined = new_df.sort_values('timestamp').reset_index(drop=True)
        
        # Apply retention policy
        if retention_days > 0:
            cutoff_ms = int((datetime.now() - timedelta(days=retention_days)).timestamp() * 1000)
            combined = combined[combined['timestamp'] >= cutoff_ms]
        
        # Save to cache
        cache_path = self._get_cache_path(symbol, interval)
        try:
            with self._lock:
                combined.to_parquet(cache_path, index=False)
            
            log.info(f"📦 Cache updated: {symbol}/{interval} | {len(combined)} rows | +{len(new_data)} new")
        except Exception as e:
            log.error(f"❌ Failed to save cache {cache_path}: {e}")
        
        return combined
    
    def get_with_incremental_fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
        fetch_func
    ) -> pd.DataFrame:
        """
        Get data with incremental fetching
        
        Args:
            symbol: Trading pair
            interval: Timeframe
            limit: Minimum number of rows needed
            fetch_func: Function to fetch new data, signature:
                        fetch_func(symbol, interval, limit, start_time=None) -> List[Dict]
                        
        Returns:
            DataFrame with at least `limit` rows
        """
        # Check cache
        cached_df = self.get_cached_data(symbol, interval)
        last_ts = self.get_last_timestamp(symbol, interval)
        
        if cached_df is not None and len(cached_df) >= limit and last_ts:
            # Cache sufficient, fetch only new data since last timestamp
            interval_ms = self.INTERVAL_MS.get(interval, 5 * 60 * 1000)
            start_time = last_ts + interval_ms  # Next candle after last cached
            
            log.info(f"📦 Cache hit: {symbol}/{interval} | {len(cached_df)} cached, fetching since {datetime.fromtimestamp(start_time/1000)}")
            
            try:
                new_data = fetch_func(symbol, interval, 100, start_time=start_time)
                if new_data:
                    combined = self.append_data(symbol, interval, new_data)
                    return combined.tail(limit)
                else:
                    return cached_df.tail(limit)
            except Exception as e:
                log.warning(f"⚠️ Incremental fetch failed, using cache: {e}")
                return cached_df.tail(limit)
        else:
            # Cache miss or insufficient, fetch full data
            log.info(f"📦 Cache miss: {symbol}/{interval} | Fetching {limit} rows")
            
            try:
                new_data = fetch_func(symbol, interval, limit, start_time=None)
                if new_data:
                    combined = self.append_data(symbol, interval, new_data)
                    return combined.tail(limit)
                return pd.DataFrame()
            except Exception as e:
                log.error(f"❌ Fetch failed: {e}")
                return cached_df.tail(limit) if cached_df is not None else pd.DataFrame()
    
    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear cache for a symbol or all symbols
        
        Args:
            symbol: Specific symbol to clear, or None for all
        """
        if symbol:
            symbol_dir = self.cache_dir / symbol.upper()
            if symbol_dir.exists():
                import shutil
                shutil.rmtree(symbol_dir)
                log.info(f"🗑️ Cache cleared: {symbol}")
        else:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                log.info("🗑️ All cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        stats = {
            'total_files': 0,
            'total_size_mb': 0,
            'symbols': {}
        }
        
        for symbol_dir in self.cache_dir.iterdir():
            if symbol_dir.is_dir():
                symbol = symbol_dir.name
                stats['symbols'][symbol] = {}
                
                for cache_file in symbol_dir.glob("*.parquet"):
                    interval = cache_file.stem
                    size_mb = cache_file.stat().st_size / (1024 * 1024)
                    
                    try:
                        df = pd.read_parquet(cache_file)
                        rows = len(df)
                    except:
                        rows = 0
                    
                    stats['symbols'][symbol][interval] = {
                        'rows': rows,
                        'size_mb': round(size_mb, 2)
                    }
                    stats['total_files'] += 1
                    stats['total_size_mb'] += size_mb
        
        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        return stats


# Global instance
_kline_cache: Optional[KlineCache] = None

def get_kline_cache() -> KlineCache:
    """Get global KlineCache instance (singleton)"""
    global _kline_cache
    if _kline_cache is None:
        _kline_cache = KlineCache()
    return _kline_cache
