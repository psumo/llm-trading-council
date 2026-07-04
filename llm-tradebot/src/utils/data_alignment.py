#!/usr/bin/env python3
"""
数据对齐辅助模块
提供多周期数据对齐和实时/滞后模式切换的工具函数

使用示例:
    from src.utils.data_alignment import DataAlignmentHelper
    
    helper = DataAlignmentHelper()
    latest_data = helper.get_aligned_candle(df, timeframe='5m')
"""

import yaml
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, Optional, Tuple
import logging


class DataAlignmentHelper:
    """数据对齐辅助类"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化数据对齐助手
        
        Args:
            config_path: 配置文件路径，默认为 config/data_alignment.yaml
        """
        self.logger = logging.getLogger(__name__)
        
        # 加载配置
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'data_alignment.yaml'
        
        self.config = self._load_config(config_path)
        self.mode = self.config.get('mode', 'backtest')
        
        # 周期时长映射（分钟）
        self.period_minutes = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720,
            '1d': 1440, '1w': 10080
        }
        
        self.logger.info(f"数据对齐助手初始化完成: mode={self.mode}")
    
    def _load_config(self, config_path: Path) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.warning(f"无法加载配置文件 {config_path}: {e}，使用默认配置")
            return {
                'mode': 'backtest',
                'timeframe_settings': {}
            }
    
    def get_aligned_candle(
        self, 
        df: pd.DataFrame, 
        timeframe: str,
        now: Optional[datetime] = None
    ) -> Tuple[pd.Series, Dict]:
        """
        根据配置获取对齐的K线数据
        
        Args:
            df: K线DataFrame（index为DatetimeIndex）
            timeframe: 周期（'5m', '15m', '1h'等）
            now: 当前时间（用于计算滞后），默认为当前UTC时间
        
        Returns:
            (candle_data, metadata)
            - candle_data: 选中的K线数据（Series）
            - metadata: 元数据字典，包含：
                - index: 使用的索引（-1或-2）
                - timestamp: K线时间
                - lag_minutes: 滞后分钟数
                - is_realtime: 是否为实时K线
                - is_completed: K线是否已完成
                - completion_pct: 完成度百分比
        """
        if len(df) < 2:
            raise ValueError(f"DataFrame长度不足: {len(df)} < 2")
        
        if now is None:
            now = datetime.now(timezone.utc)
        
        # 获取该周期的配置
        settings = self.config.get('timeframe_settings', {}).get(timeframe, {})
        
        # 决定使用实时还是滞后数据
        use_realtime = self._should_use_realtime(timeframe, settings)
        
        if use_realtime:
            # 尝试使用实时K线
            candle = df.iloc[-1]
            index = -1
            
            # 计算完成度
            completion_pct = self._calculate_completion(df, timeframe, now)
            is_completed = completion_pct >= 100.0
            
            # 检查最小完成度要求
            min_completion = settings.get('min_completion_pct', 0)
            if completion_pct < min_completion:
                self.logger.warning(
                    f"[{timeframe}] K线完成度 {completion_pct:.1f}% < {min_completion}%，"
                    f"降级使用已完成K线"
                )
                candle = df.iloc[-2]
                index = -2
                completion_pct = 100.0
                is_completed = True
        else:
            # 使用已完成K线
            candle = df.iloc[-2]
            index = -2
            completion_pct = 100.0
            is_completed = True
        
        # 计算元数据
        timestamp = df.index[index]
        lag_minutes = self._calculate_lag_minutes(timestamp, now)
        
        metadata = {
            'index': index,
            'timestamp': timestamp,
            'lag_minutes': lag_minutes,
            'is_realtime': (index == -1),
            'is_completed': is_completed,
            'completion_pct': completion_pct,
            'timeframe': timeframe,
            'mode': self.mode
        }
        
        # 检查滞后告警
        self._check_lag_warning(timeframe, lag_minutes, settings)
        
        return candle, metadata
    
    def _should_use_realtime(self, timeframe: str, settings: Dict) -> bool:
        """判断是否应该使用实时K线"""
        
        # 回测模式：始终使用已完成K线
        if self.mode == 'backtest':
            return False
        
        # 实盘模式：根据配置决定
        use_realtime = settings.get('use_realtime', False)
        
        # live_aggressive模式：默认启用实时（除非显式禁用）
        if self.mode == 'live_aggressive' and 'use_realtime' not in settings:
            return True
        
        return use_realtime
    
    def _calculate_completion(
        self, 
        df: pd.DataFrame, 
        timeframe: str, 
        now: datetime
    ) -> float:
        """
        计算当前K线的完成度百分比
        
        Returns:
            完成度（0-100）
        """
        if len(df) < 1:
            return 0.0
        
        last_time = df.index[-1]
        
        # 确保时区一致
        if last_time.tzinfo is None and now.tzinfo is not None:
            last_time = last_time.tz_localize('UTC')
        elif last_time.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        
        # 获取周期长度
        period_minutes = self.period_minutes.get(timeframe, 5)
        
        # 计算K线应该的结束时间
        candle_end = last_time + pd.Timedelta(minutes=period_minutes)
        
        # 已完成
        if now >= candle_end:
            return 100.0
        
        # 计算完成度
        elapsed = (now - last_time).total_seconds()
        total = period_minutes * 60
        completion = (elapsed / total) * 100
        
        return max(0.0, min(100.0, completion))
    
    def _calculate_lag_minutes(self, data_time: pd.Timestamp, current_time: datetime) -> float:
        """计算数据滞后分钟数"""
        
        # 确保时区一致
        if data_time.tzinfo is None and current_time.tzinfo is not None:
            data_time = data_time.tz_localize('UTC')
        elif data_time.tzinfo is not None and current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        
        lag_seconds = (current_time - data_time).total_seconds()
        return lag_seconds / 60.0
    
    def _check_lag_warning(self, timeframe: str, lag_minutes: float, settings: Dict):
        """检查滞后是否超过阈值并发出警告"""
        
        threshold = settings.get('lag_warning_threshold', 
                                self.config.get('lag_detection', {}).get('warning_threshold_minutes', 30))
        
        if lag_minutes > threshold:
            self.logger.warning(
                f"[{timeframe}] 数据滞后告警: {lag_minutes:.1f}分钟 > {threshold}分钟阈值"
            )
    
    def get_multi_timeframe_metadata(
        self, 
        timeframe_data: Dict[str, pd.DataFrame],
        now: Optional[datetime] = None
    ) -> Dict:
        """
        获取多周期数据的元数据和时间错位分析
        
        Args:
            timeframe_data: {timeframe: DataFrame} 字典
            now: 当前时间
        
        Returns:
            元数据字典，包含：
            - timeframes: {timeframe: metadata}
            - time_gap_minutes: 最大时间差（分钟）
            - earliest_timestamp: 最早的数据时间
            - latest_timestamp: 最晚的数据时间
            - max_lag_minutes: 最大滞后
        """
        if now is None:
            now = datetime.now(timezone.utc)
        
        timeframes_meta = {}
        timestamps = []
        
        for timeframe, df in timeframe_data.items():
            try:
                _, metadata = self.get_aligned_candle(df, timeframe, now)
                timeframes_meta[timeframe] = metadata
                timestamps.append(metadata['timestamp'])
            except Exception as e:
                self.logger.error(f"[{timeframe}] 获取元数据失败: {e}")
        
        if not timestamps:
            return {}
        
        # 计算时间错位
        earliest = min(timestamps)
        latest = max(timestamps)
        time_gap = self._calculate_lag_minutes(earliest, latest)
        
        # 计算最大滞后
        max_lag = max([meta['lag_minutes'] for meta in timeframes_meta.values()])
        
        result = {
            'timeframes': timeframes_meta,
            'time_gap_minutes': time_gap,
            'earliest_timestamp': earliest,
            'latest_timestamp': latest,
            'max_lag_minutes': max_lag,
            'current_time': now
        }
        
        # 时间错位告警
        gap_threshold = self.config.get('lag_detection', {}).get('time_gap_threshold_minutes', 60)
        if time_gap > gap_threshold:
            self.logger.warning(
                f"⚠️ 多周期时间错位严重: {time_gap:.1f}分钟 > {gap_threshold}分钟阈值"
            )
        
        return result
    
    def format_metadata_log(self, metadata: Dict) -> str:
        """格式化元数据为日志字符串"""
        
        if 'timeframes' in metadata:
            # 多周期元数据
            lines = ["多周期数据状态:"]
            for tf, meta in metadata['timeframes'].items():
                status = "实时" if meta['is_realtime'] else "滞后"
                lines.append(
                    f"  [{tf:3s}] {meta['timestamp'].strftime('%H:%M:%S')} | "
                    f"滞后: {meta['lag_minutes']:5.1f}min | "
                    f"完成度: {meta['completion_pct']:5.1f}% | "
                    f"模式: {status}"
                )
            lines.append(f"  时间错位: {metadata['time_gap_minutes']:.1f}分钟")
            lines.append(f"  最大滞后: {metadata['max_lag_minutes']:.1f}分钟")
            return "\n".join(lines)
        else:
            # 单周期元数据
            status = "实时" if metadata['is_realtime'] else "滞后"
            return (
                f"[{metadata['timeframe']}] "
                f"时间: {metadata['timestamp'].strftime('%H:%M:%S')} | "
                f"滞后: {metadata['lag_minutes']:.1f}min | "
                f"完成度: {metadata['completion_pct']:.1f}% | "
                f"模式: {status}"
            )


# 便捷函数
def get_aligned_candle(df: pd.DataFrame, timeframe: str, config_path: Optional[str] = None):
    """
    便捷函数：获取对齐的K线数据
    
    使用示例:
        from src.utils.data_alignment import get_aligned_candle
        
        candle, metadata = get_aligned_candle(df, '5m')
        print(f"使用的数据: {metadata['timestamp']}, 滞后: {metadata['lag_minutes']}分钟")
    """
    helper = DataAlignmentHelper(config_path)
    return helper.get_aligned_candle(df, timeframe)


if __name__ == "__main__":
    # 简单测试
    logging.basicConfig(level=logging.INFO)
    
    # 创建测试数据
    timestamps = pd.date_range('2025-12-18 16:00:00', periods=100, freq='5min', tz='UTC')
    df = pd.DataFrame({
        'open': 88000,
        'high': 88100,
        'low': 87900,
        'close': 88050,
        'volume': 1000
    }, index=timestamps)
    
    # 测试
    helper = DataAlignmentHelper()
    candle, metadata = helper.get_aligned_candle(df, '5m')
    
    print("测试结果:")
    print(helper.format_metadata_log(metadata))
