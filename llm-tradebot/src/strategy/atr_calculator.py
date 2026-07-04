"""
ATR-based Dynamic TP/SL Calculator
===================================

Calculates dynamic take profit and stop loss multipliers based on 
Average True Range (ATR) to adapt to market volatility.

Author: AI Trader Team
Date: 2026-01-23
"""

import pandas as pd
from typing import Dict


class ATRCalculator:
    """
    ATR-based calculator for dynamic TP/SL adjustment
    
    Maps market volatility (ATR) to multipliers:
    - Low volatility (ATR < 0.5%): 1.0x (conservative)
    - High volatility (ATR > 2.0%): 2.0x (aggressive)
    """
    
    def __init__(self, period: int = 14):
        """
        Initialize ATR calculator
        
        Args:
            period: ATR calculation period (default: 14)
        """
        self.period = period
    
    def calculate_atr(self, df: pd.DataFrame) -> float:
        """
        Calculate Average True Range
        
        Args:
            df: DataFrame with 'high', 'low', 'close' columns
            
        Returns:
            ATR value
        """
        if len(df) < self.period:
            return 0.0
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range components
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        # True Range = max of three components
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR = moving average of TR
        atr = tr.rolling(self.period).mean().iloc[-1]
        
        return atr
    
    def calculate_atr_percentage(self, df: pd.DataFrame) -> float:
        """
        Calculate ATR as percentage of current price
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            ATR percentage (e.g., 1.5 for 1.5%)
        """
        if len(df) < self.period:
            return 1.0  # Default 1%
        
        atr = self.calculate_atr(df)
        current_price = df['close'].iloc[-1]
        
        if current_price == 0:
            return 1.0
        
        atr_pct = (atr / current_price) * 100
        return atr_pct
    
    def calculate_multiplier(self, df: pd.DataFrame) -> float:
        """
        Calculate TP/SL multiplier based on ATR
        
        Mapping:
        - ATR < 0.5%: 1.0x (low volatility, conservative targets)
        - ATR 0.5-2.0%: 1.0x - 2.0x (linear scaling)
        - ATR > 2.0%: 2.0x (high volatility, wider targets)
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            Multiplier between 1.0 and 2.0
        """
        atr_pct = self.calculate_atr_percentage(df)
        
        # Map ATR percentage to multiplier
        if atr_pct < 0.5:
            return 1.0
        elif atr_pct > 2.0:
            return 2.0
        else:
            # Linear interpolation: 0.5% -> 1.0x, 2.0% -> 2.0x
            return 1.0 + (atr_pct - 0.5) / 1.5
    
    def get_analysis(self, df: pd.DataFrame) -> Dict:
        """
        Get comprehensive ATR analysis
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            Dict with ATR value, percentage, multiplier, and volatility level
        """
        if len(df) < self.period:
            return {
                'atr': 0.0,
                'atr_pct': 0.0,
                'multiplier': 1.0,
                'volatility': 'insufficient_data'
            }
        
        atr = self.calculate_atr(df)
        atr_pct = self.calculate_atr_percentage(df)
        multiplier = self.calculate_multiplier(df)
        
        # Classify volatility
        if atr_pct < 0.5:
            volatility = 'low'
        elif atr_pct < 1.0:
            volatility = 'normal'
        elif atr_pct < 2.0:
            volatility = 'elevated'
        else:
            volatility = 'high'
        
        return {
            'atr': round(atr, 2),
            'atr_pct': round(atr_pct, 2),
            'multiplier': round(multiplier, 2),
            'volatility': volatility
        }
