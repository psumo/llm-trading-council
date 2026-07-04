"""
5min Trigger Detector (Specification Module 4)

Purpose:
- Detect precise entry signals on 5min timeframe
- Pattern A: Bullish Engulfing (阳包阴)
- Pattern B: Volume Breakout (放量突破)

Specification:
- Data: Last 10 bars of 5min K-lines
- Volume MA3: Average of last 3 bars
- Engulfing: Previous bearish + Current bullish包住
- Breakout: Close > max(prev 3 highs) + Volume > 1.5 × MA3
"""

import pandas as pd
from typing import Dict
from src.utils.logger import log


class TriggerDetector:
    """
    5min Trigger Pattern Detector
    
    Implements specification Module 4: Trigger (扳机模块)
    """
    
    def __init__(self):
        """Initialize trigger detector"""
        pass
    
    def detect_engulfing(self, df_5m: pd.DataFrame, direction: str = 'long') -> Dict:
        """
        Detect Engulfing pattern (阳包阴 for long, 阴包阳 for short)
        
        Specification:
        - Previous candle: Bearish (Close < Open)
        - Current candle: Bullish (Close > Open) AND包住previous
        - Confirmation: Wait for candle close
        
        Args:
            df_5m: 5min K-line data
            direction: 'long' or 'short'
            
        Returns:
            {
                'detected': bool,
                'pattern': str,
                'prev_candle': dict,
                'curr_candle': dict
            }
        """
        if len(df_5m) < 2:
            return {'detected': False, 'pattern': None}
        
        prev = df_5m.iloc[-2]
        curr = df_5m.iloc[-1]
        
        if direction == 'long':
            # 前一根是阴线
            prev_bearish = prev['close'] < prev['open']
            # 当前是阳线
            curr_bullish = curr['close'] > curr['open']
            # 阳线包住阴线
            engulfing = curr['close'] > prev['open'] and curr['open'] < prev['close']
            
            detected = prev_bearish and curr_bullish and engulfing
            
        else:  # short
            # 前一根是阳线
            prev_bullish = prev['close'] > prev['open']
            # 当前是阴线
            curr_bearish = curr['close'] < curr['open']
            # 阴线包住阳线
            engulfing = curr['close'] < prev['open'] and curr['open'] > prev['close']
            
            detected = prev_bullish and curr_bearish and engulfing
        
        if detected:
            log.info(f"🎯 Engulfing pattern detected ({direction}): "
                    f"Prev [{prev['open']:.2f}->{prev['close']:.2f}], "
                    f"Curr [{curr['open']:.2f}->{curr['close']:.2f}]")
        
        return {
            'detected': detected,
            'pattern': 'engulfing',
            'prev_candle': {
                'open': prev['open'],
                'close': prev['close'],
                'high': prev['high'],
                'low': prev['low']
            },
            'curr_candle': {
                'open': curr['open'],
                'close': curr['close'],
                'high': curr['high'],
                'low': curr['low']
            }
        }
    
    def detect_breakout(self, df_5m: pd.DataFrame, direction: str = 'long', sensitivity: float = 1.0) -> Dict:
        """
        Detect Volume Breakout (放量突破)
        
        Specification:
        - Price: Close > max(prev 3 highs) for long
        - Volume: Current > 1.5 × MA3
        - Timing: Can enter immediately, no need to wait for close
        
        Args:
            df_5m: 5min K-line data
            direction: 'long' or 'short'
            
        Returns:
            {
                'detected': bool,
                'pattern': str,
                'breakout_level': float,
                'volume_ratio': float
            }
        """
        if len(df_5m) < 4:
            return {'detected': False, 'pattern': None}
        
        curr = df_5m.iloc[-1]
        prev_3 = df_5m.iloc[-4:-1]
        
        # Calculate Volume MA3
        vol_ma3 = prev_3['volume'].mean()
        volume_ratio = curr['volume'] / vol_ma3 if vol_ma3 > 0 else 0
        
        if direction == 'long':
            # 突破前3根高点
            breakout_level = prev_3['high'].max()
            price_breakout = curr['close'] > breakout_level
        else:  # short
            # 跌破前3根低点
            breakout_level = prev_3['low'].min()
            price_breakout = curr['close'] < breakout_level
        
        sens = max(0.75, min(1.2, float(sensitivity or 1.0)))
        # 动态量能阈值: 趋势延续阶段允许更低确认门槛
        avg_prev_range = (prev_3['high'] - prev_3['low']).mean()
        curr_range = max(float(curr['high'] - curr['low']), 0.0)
        range_ratio = (curr_range / avg_prev_range) if avg_prev_range > 0 else 1.0
        volume_threshold = (0.85 if range_ratio >= 0.9 else 1.0) * sens
        volume_threshold = max(0.7, min(1.2, volume_threshold))
        volume_confirm = volume_ratio >= volume_threshold
        
        detected = price_breakout and volume_confirm
        
        if detected:
            log.info(f"🚀 Breakout detected ({direction}): "
                    f"Price {curr['close']:.2f} {'>' if direction == 'long' else '<'} {breakout_level:.2f}, "
                    f"Volume ratio {volume_ratio:.2f}x")
        
        return {
            'detected': detected,
            'pattern': 'breakout',
            'breakout_level': breakout_level,
            'volume_ratio': volume_ratio,
            'volume_threshold': float(volume_threshold),
            'current_price': curr['close'],
            'current_volume': curr['volume'],
            'vol_ma3': vol_ma3
        }

    def detect_continuation(self, df_5m: pd.DataFrame, direction: str = 'long', sensitivity: float = 1.0) -> Dict:
        """
        Detect trend continuation pattern (break-retest-resume style).
        """
        if len(df_5m) < 8:
            return {'detected': False, 'pattern': None}

        sens = max(0.75, min(1.2, float(sensitivity or 1.0)))
        curr = df_5m.iloc[-1]
        prev_1 = df_5m.iloc[-2]
        prev_2 = df_5m.iloc[-3]
        lookback = df_5m.iloc[-8:-1]
        if lookback.empty:
            return {'detected': False, 'pattern': None}

        swing_high = float(lookback['high'].max())
        swing_low = float(lookback['low'].min())
        avg_volume = float(lookback['volume'].mean()) if 'volume' in lookback.columns else 0.0
        avg_range = float((lookback['high'] - lookback['low']).mean())
        curr_range = max(float(curr['high'] - curr['low']), 0.0)
        body = abs(float(curr['close'] - curr['open']))
        body_ratio = (body / curr_range) if curr_range > 0 else 0.0
        close_5ago = float(df_5m['close'].iloc[-6]) if len(df_5m) >= 6 else float(prev_2['close'])
        rvol = self.calculate_rvol(df_5m, lookback=8)

        structure_tolerance = max(0.985, min(1.01, 0.995 - (1.0 - sens) * 0.02))
        if direction == 'long':
            trend_bias = float(prev_1['close']) > close_5ago
            resumed = float(curr['close']) > float(curr['open']) and float(curr['close']) >= float(prev_1['close'])
            structure_ok = float(curr['close']) >= swing_high * structure_tolerance
        else:
            trend_bias = float(prev_1['close']) < close_5ago
            resumed = float(curr['close']) < float(curr['open']) and float(curr['close']) <= float(prev_1['close'])
            structure_ok = float(curr['close']) <= swing_low * (2 - structure_tolerance)

        volatility_ok = True if avg_range <= 0 else (curr_range >= avg_range * (0.7 * sens))
        volume_ok = (float(curr['volume']) >= avg_volume * (0.8 * sens)) if avg_volume > 0 else True
        momentum_ok = body_ratio >= (0.35 * sens)
        rvol_ok = rvol >= (0.7 * sens)
        detected = bool(trend_bias and resumed and structure_ok and volatility_ok and momentum_ok and (volume_ok or rvol_ok))

        if detected:
            log.info(
                f"⚡ Continuation detected ({direction}): close={float(curr['close']):.4f}, "
                f"structure={'HIGH' if direction == 'long' else 'LOW'} hit, RVOL={rvol:.2f}x"
            )

        return {
            'detected': detected,
            'pattern': 'continuation',
            'structure_level': swing_high if direction == 'long' else swing_low,
            'rvol': rvol,
            'body_ratio': body_ratio,
            'volume_ok': volume_ok,
            'volatility_ok': volatility_ok
        }

    def detect_trigger(self, df_5m: pd.DataFrame, direction: str = 'long', sensitivity: float = 1.0) -> Dict:
        """
        Detect any trigger pattern (Engulfing OR Breakout)
        
        Args:
            df_5m: 5min K-line data
            direction: 'long' or 'short'
            
        Returns:
            {
                'triggered': bool,
                'pattern_type': 'engulfing' | 'breakout' | None,
                'details': dict,
                'rvol': float  # 🆕 Relative Volume
            }
        """
        # Check engulfing
        engulfing_result = self.detect_engulfing(df_5m, direction)
        
        # Check breakout
        breakout_result = self.detect_breakout(df_5m, direction, sensitivity=sensitivity)

        # Check continuation
        continuation_result = self.detect_continuation(df_5m, direction, sensitivity=sensitivity)

        # 🆕 Calculate RVOL (Relative Volume vs 10-period average)
        rvol = self.calculate_rvol(df_5m)
        
        if engulfing_result['detected']:
            return {
                'triggered': True,
                'pattern_type': 'engulfing',
                'details': engulfing_result,
                'rvol': rvol
            }
        elif breakout_result['detected']:
            return {
                'triggered': True,
                'pattern_type': 'breakout',
                'details': breakout_result,
                'rvol': rvol
            }
        elif continuation_result['detected']:
            return {
                'triggered': True,
                'pattern_type': 'continuation',
                'details': continuation_result,
                'rvol': max(rvol, continuation_result.get('rvol', rvol))
            }
        # RVOL fallback: require basic momentum quality to avoid chop false-triggers
        elif rvol >= (0.65 * max(0.75, min(1.2, float(sensitivity or 1.0)))):
            # 检查价格动量 (当前K线方向与交易方向一致)
            if len(df_5m) >= 2:
                curr = df_5m.iloc[-1]
                prev = df_5m.iloc[-2]
                avg_range = None
                if len(df_5m) >= 6:
                    avg_range = (df_5m['high'].iloc[-6:-1] - df_5m['low'].iloc[-6:-1]).mean()
                curr_range = float(curr['high'] - curr['low']) if float(curr['high'] - curr['low']) > 0 else 0.0
                body = abs(float(curr['close'] - curr['open']))
                body_ratio = (body / curr_range) if curr_range > 0 else 0.0
                momentum_ok = False
                if (
                    direction == 'long'
                    and curr['close'] > curr['open']
                    and prev['close'] > prev['open']
                    and curr['close'] > prev['close']
                ):
                    momentum_ok = True
                elif (
                    direction == 'short'
                    and curr['close'] < curr['open']
                    and prev['close'] < prev['open']
                    and curr['close'] < prev['close']
                ):
                    momentum_ok = True

                quality_ok = body_ratio >= 0.3
                if avg_range is not None and avg_range > 0:
                    quality_ok = quality_ok and (curr_range >= avg_range * 0.55)

                if momentum_ok and quality_ok:
                    log.info(f"📊 RVOL trigger activated ({direction}): RVOL={rvol:.2f}x with momentum")
                    return {
                        'triggered': True,
                        'pattern_type': 'rvol_momentum',
                        'details': {'rvol': rvol, 'momentum': True, 'body_ratio': body_ratio},
                        'rvol': rvol
                    }
        
        return {
            'triggered': False,
            'pattern_type': None,
            'details': {},
            'rvol': rvol
        }
    
    def calculate_rvol(self, df: pd.DataFrame, lookback: int = 10) -> float:
        """
        Calculate Relative Volume (RVOL)
        
        RVOL = Current Volume / Average Volume (last N bars)
        
        Interpretation:
        - RVOL > 1.5: High relative volume, significant interest
        - RVOL > 2.0: Very high volume, potential institutional activity
        - RVOL < 0.5: Low volume, weak conviction
        
        Args:
            df: K-line data with 'volume' column
            lookback: Number of bars for average calculation
            
        Returns:
            RVOL ratio (float)
        """
        if len(df) < lookback + 1 or 'volume' not in df.columns:
            return 1.0
        
        current_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].iloc[-lookback-1:-1].mean()
        
        if avg_vol > 0:
            return current_vol / avg_vol
        return 1.0
