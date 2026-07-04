"""
位置感知模块 (Position Analyzer)
计算当前价格在最近区间的位置，用于过滤低质量交易
"""

import pandas as pd
from typing import Dict, Tuple
from enum import Enum


class PriceLocation(Enum):
    """价格位置分类"""
    SUPPORT = "support"      # 支撑位附近 (0-20%)
    LOWER = "lower"          # 中下部 (20-40%)
    MIDDLE = "middle"        # 区间中部 (40-60%)
    UPPER = "upper"          # 中上部 (60-80%)
    RESISTANCE = "resistance"  # 阻力位附近 (80-100%)


class PositionQuality(Enum):
    """位置质量评级"""
    EXCELLENT = "excellent"  # 优秀（支撑/阻力）
    GOOD = "good"           # 良好（中下/中上）
    POOR = "poor"           # 较差（接近中部）
    TERRIBLE = "terrible"   # 极差（区间中部）


class PositionAnalyzer:
    """
    位置感知分析器
    
    核心功能：
    1. 计算价格在最近区间的位置百分比
    2. 判断位置质量
    3. 提供开仓建议（允许做多/做空）
    
    核心理念：
    - 只在支撑位附近做多
    - 只在阻力位附近做空
    - 禁止在区间中部（40-60%）开仓
    """
    
    def __init__(self, 
                 lookback_4h: int = 48,   # 4小时区间（48根5分钟K线）
                 lookback_1d: int = 288):  # 1天区间（288根5分钟K线）
        """
        初始化位置分析器
        
        Args:
            lookback_4h: 4小时区间的K线数量
            lookback_1d: 1天区间的K线数量
        """
        self.lookback_4h = lookback_4h
        self.lookback_1d = lookback_1d
        
    def analyze_position(self, 
                        df: pd.DataFrame, 
                        current_price: float,
                        timeframe: str = '5m') -> Dict:
        """
        分析价格位置
        
        Args:
            df: K线数据（必须包含 'high' 和 'low' 列）
            current_price: 当前价格
            timeframe: 时间周期（用于确定 lookback）
            
        Returns:
            {
                'range_high': float,        # 区间最高价
                'range_low': float,         # 区间最低价
                'range_size': float,        # 区间大小
                'position_pct': float,      # 位置百分比 (0-100)
                'location': PriceLocation,  # 位置分类
                'quality': PositionQuality, # 质量评级
                'allow_long': bool,         # 是否允许做多
                'allow_short': bool,        # 是否允许做空
                'reason': str               # 分析原因
            }
        """
        
        # 1. 确定 lookback 周期
        if timeframe == '5m':
            lookback = self.lookback_4h  # 4小时
        elif timeframe == '15m':
            lookback = self.lookback_4h // 3  # 约4小时
        elif timeframe == '1h':
            lookback = self.lookback_4h // 12  # 约4小时
        else:
            lookback = self.lookback_4h
        
        # 确保有足够的数据
        lookback = min(lookback, len(df))
        
        # 2. 计算区间高低点
        recent_data = df.tail(lookback)
        range_high = recent_data['high'].max()
        range_low = recent_data['low'].min()
        range_size = range_high - range_low
        
        # 3. 计算位置百分比
        if range_size == 0:
            # 区间为0（极少见），返回中性
            position_pct = 50.0
        else:
            position_pct = ((current_price - range_low) / range_size) * 100
            position_pct = max(0, min(100, position_pct))  # 限制在 0-100
        
        # 4. 判断位置分类
        location = self._classify_location(position_pct)
        
        # 5. 判断质量评级
        quality = self._classify_quality(position_pct)
        
        # 6. 判断是否允许开仓
        allow_long, allow_short = self._check_allow_trade(position_pct, location)
        
        # 7. 生成分析原因
        reason = self._generate_reason(position_pct, location, quality, range_high, range_low)
        
        return {
            'range_high': range_high,
            'range_low': range_low,
            'range_size': range_size,
            'position_pct': position_pct,
            'location': location.value,
            'quality': quality.value,
            'allow_long': allow_long,
            'allow_short': allow_short,
            'reason': reason
        }
    
    def _classify_location(self, position_pct: float) -> PriceLocation:
        """
        分类价格位置
        
        Args:
            position_pct: 位置百分比
            
        Returns:
            PriceLocation
        """
        if position_pct <= 20:
            return PriceLocation.SUPPORT
        elif position_pct <= 40:
            return PriceLocation.LOWER
        elif position_pct <= 60:
            return PriceLocation.MIDDLE
        elif position_pct <= 80:
            return PriceLocation.UPPER
        else:
            return PriceLocation.RESISTANCE
    
    def _classify_quality(self, position_pct: float) -> PositionQuality:
        """
        评估位置质量
        
        Args:
            position_pct: 位置百分比
            
        Returns:
            PositionQuality
        """
        if position_pct <= 15 or position_pct >= 85:
            # 非常接近支撑/阻力
            return PositionQuality.EXCELLENT
        elif position_pct <= 30 or position_pct >= 70:
            # 接近支撑/阻力
            return PositionQuality.GOOD
        elif 45 <= position_pct <= 55:
            # 区间正中部
            return PositionQuality.TERRIBLE
        else:
            # 其他（接近中部）
            return PositionQuality.POOR
    
    def _check_allow_trade(self, 
                          position_pct: float, 
                          location: PriceLocation) -> Tuple[bool, bool]:
        """
        检查是否允许开仓
        
        规则：
        - 做多：只在支撑位和中下部（0-40%）
        - 做空：只在阻力位和中上部（60-100%）
        - 区间中部（40-60%）：禁止开仓
        
        Args:
            position_pct: 位置百分比
            location: 位置分类
            
        Returns:
            (allow_long, allow_short)
        """
        # 区间中部：禁止任何开仓
        if 40 <= position_pct <= 60:
            return False, False
        
        # 做多：只在下半部分
        allow_long = position_pct < 60
        
        # 做空：只在上半部分
        allow_short = position_pct > 40
        
        return allow_long, allow_short
    
    def _generate_reason(self, 
                        position_pct: float,
                        location: PriceLocation,
                        quality: PositionQuality,
                        range_high: float,
                        range_low: float) -> str:
        """
        生成分析原因
        
        Args:
            position_pct: 位置百分比
            location: 位置分类
            quality: 质量评级
            range_high: 区间最高价
            range_low: 区间最低价
            
        Returns:
            原因描述
        """
        location_desc = {
            PriceLocation.SUPPORT: "支撑位附近",
            PriceLocation.LOWER: "中下部",
            PriceLocation.MIDDLE: "区间中部",
            PriceLocation.UPPER: "中上部",
            PriceLocation.RESISTANCE: "阻力位附近"
        }
        
        quality_desc = {
            PositionQuality.EXCELLENT: "优秀",
            PositionQuality.GOOD: "良好",
            PositionQuality.POOR: "较差",
            PositionQuality.TERRIBLE: "极差"
        }
        
        reason = f"价格位置: {position_pct:.1f}% ({location_desc[location]}), "
        reason += f"质量: {quality_desc[quality]}, "
        reason += f"区间: ${range_low:.2f} - ${range_high:.2f}"
        
        return reason


# 测试代码
if __name__ == '__main__':
    import numpy as np
    
    # 创建测试数据
    dates = pd.date_range('2025-01-01', periods=100, freq='5min')
    prices = 87000 + np.cumsum(np.random.randn(100) * 50)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'high': prices + np.random.rand(100) * 20,
        'low': prices - np.random.rand(100) * 20,
        'close': prices
    })
    
    analyzer = PositionAnalyzer()
    
    # 测试不同位置
    test_prices = [
        (df['low'].min() + 50, "接近支撑"),
        ((df['high'].max() + df['low'].min()) / 2, "区间中部"),
        (df['high'].max() - 50, "接近阻力")
    ]
    
    print("位置分析测试:\n")
    for price, desc in test_prices:
        result = analyzer.analyze_position(df, price)
        print(f"{desc}:")
        print(f"  价格: ${price:.2f}")
        print(f"  位置: {result['position_pct']:.1f}%")
        print(f"  分类: {result['location']}")
        print(f"  质量: {result['quality']}")
        print(f"  允许做多: {result['allow_long']}")
        print(f"  允许做空: {result['allow_short']}")
        print(f"  原因: {result['reason']}")
        print()
