"""
技术特征工程模块

基于 Step2 的技术指标构建高级特征，用于：
1. 规则策略的增强决策
2. 机器学习模型训练
3. LLM 上下文输入

设计原则：
- 输入：Step2 的 31 列技术指标
- 输出：50+ 列高级特征
- 所有特征都有明确的金融意义
- 避免数据泄露（不使用未来数据）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from src.utils.logger import log


class TechnicalFeatureEngineer:
    """技术特征工程器"""
    
    # 特征版本（用于追踪特征定义变更）
    FEATURE_VERSION = 'v1.0'
    
    def __init__(self):
        self.feature_count = 0
        self.feature_names = []
    
    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        基于技术指标构建高级特征
        
        Args:
            df: Step2 输出的 DataFrame（含技术指标）
            
        Returns:
            扩展后的 DataFrame（原有列 + 新增特征列）
            
        特征分类：
        1. 价格相对位置特征（8个）
        2. 趋势强度特征（10个）
        3. 动量特征（8个）
        4. 波动率特征（8个）
        5. 成交量特征（8个）
        6. 多指标组合特征（8个）
        """
        log.info(f"开始特征工程: 原始列数={len(df.columns)}")
        
        # 复制数据，避免修改原始 DataFrame
        df_features = df.copy()
        
        # 1. 价格相对位置特征
        df_features = self._build_price_position_features(df_features)
        
        # 2. 趋势强度特征
        df_features = self._build_trend_strength_features(df_features)
        
        # 3. 动量特征
        df_features = self._build_momentum_features(df_features)
        
        # 4. 波动率特征
        df_features = self._build_volatility_features(df_features)
        
        # 5. 成交量特征
        df_features = self._build_volume_features(df_features)
        
        # 6. 多指标组合特征
        df_features = self._build_composite_features(df_features)
        
        # 记录特征信息
        new_features = set(df_features.columns) - set(df.columns)
        self.feature_count = len(new_features)
        self.feature_names = sorted(list(new_features))
        
        log.info(
            f"特征工程完成: 新增特征={self.feature_count}, "
            f"总列数={len(df_features.columns)}"
        )
        
        # 添加特征元数据
        df_features.attrs['feature_version'] = self.FEATURE_VERSION
        df_features.attrs['feature_count'] = self.feature_count
        df_features.attrs['feature_names'] = self.feature_names
        
        return df_features
    
    def _build_price_position_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        构建价格相对位置特征
        
        金融意义：衡量当前价格在各种技术参考点的位置
        """
        # 1. 价格相对于移动平均线的位置
        df['price_to_sma20_pct'] = ((df['close'] - df['sma_20']) / df['sma_20'] * 100)
        df['price_to_sma50_pct'] = ((df['close'] - df['sma_50']) / df['sma_50'] * 100)
        df['price_to_ema12_pct'] = ((df['close'] - df['ema_12']) / df['ema_12'] * 100)
        df['price_to_ema26_pct'] = ((df['close'] - df['ema_26']) / df['ema_26'] * 100)
        
        # 2. 价格在布林带中的位置（0-100，50为中轴）
        df['bb_position'] = np.where(
            (df['bb_upper'] - df['bb_lower']) > 0,
            (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']) * 100,
            50  # 布林带宽度为0时，认为在中轴
        )
        
        # 3. 价格相对于 VWAP 的偏离
        df['price_to_vwap_pct'] = np.where(
            df['vwap'] > 0,
            (df['close'] - df['vwap']) / df['vwap'] * 100,
            0
        )
        
        # 4. 当前价格在最近 K 线高低点的位置
        df['price_to_recent_high_pct'] = (
            (df['close'] - df['high'].rolling(20).max()) / 
            df['high'].rolling(20).max() * 100
        )
        df['price_to_recent_low_pct'] = (
            (df['close'] - df['low'].rolling(20).min()) / 
            df['low'].rolling(20).min() * 100
        )
        
        return df
    
    def _build_trend_strength_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        构建趋势强度特征
        
        金融意义：衡量市场趋势的强度和方向
        """
        # 1. EMA 交叉强度（快线与慢线的距离）
        df['ema_cross_strength'] = (df['ema_12'] - df['ema_26']) / df['close'] * 100
        
        # 2. SMA 交叉强度
        df['sma_cross_strength'] = (df['sma_20'] - df['sma_50']) / df['close'] * 100
        
        # 3. MACD 动量（当前 MACD 与历史的比较）
        df['macd_momentum_5'] = df['macd'] - df['macd'].shift(5)
        df['macd_momentum_10'] = df['macd'] - df['macd'].shift(10)
        
        # 4. 趋势一致性（EMA 和 SMA 是否同向）
        df['trend_alignment'] = np.where(
            (df['ema_cross_strength'] > 0) & (df['sma_cross_strength'] > 0),
            1,  # 双重上涨
            np.where(
                (df['ema_cross_strength'] < 0) & (df['sma_cross_strength'] < 0),
                -1,  # 双重下跌
                0  # 方向不一致
            )
        )
        
        # 5. 价格趋势斜率（线性回归斜率）
        def calc_slope(series):
            if len(series) < 2:
                return 0
            x = np.arange(len(series))
            try:
                slope = np.polyfit(x, series, 1)[0]
                return slope / series.iloc[-1] * 100 if series.iloc[-1] != 0 else 0
            except:
                return 0
        
        df['price_slope_5'] = df['close'].rolling(5).apply(calc_slope, raw=False)
        df['price_slope_10'] = df['close'].rolling(10).apply(calc_slope, raw=False)
        df['price_slope_20'] = df['close'].rolling(20).apply(calc_slope, raw=False)
        
        # 6. ADX 替代指标：方向性强度
        # 使用价格变化的方向一致性来衡量趋势强度
        df['directional_strength'] = (
            df['close'].diff().rolling(14).apply(
                lambda x: (x > 0).sum() / len(x) * 100 if len(x) > 0 else 50,
                raw=False
            )
        )
        
        return df
    
    def _build_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        构建动量特征
        
        金融意义：衡量价格变化的速度和加速度
        """
        # 1. RSI 动量（RSI 的变化率）
        df['rsi_momentum_5'] = df['rsi'] - df['rsi'].shift(5)
        df['rsi_momentum_10'] = df['rsi'] - df['rsi'].shift(10)
        
        # 2. RSI 区域（离散化）
        df['rsi_zone'] = pd.cut(
            df['rsi'],
            bins=[0, 30, 40, 60, 70, 100],
            labels=['oversold', 'weak', 'neutral', 'strong', 'overbought']
        )
        # 转换为数值（用于计算）
        df['rsi_zone_numeric'] = pd.cut(
            df['rsi'],
            bins=[0, 30, 40, 60, 70, 100],
            labels=[-2, -1, 0, 1, 2]
        ).astype(float)
        
        # 3. 价格动量（多周期收益率）
        df['return_1'] = df['close'].pct_change(1) * 100
        df['return_5'] = df['close'].pct_change(5) * 100
        df['return_10'] = df['close'].pct_change(10) * 100
        df['return_20'] = df['close'].pct_change(20) * 100
        
        # 4. 动量加速度（收益率的变化）
        df['momentum_acceleration'] = df['return_5'] - df['return_5'].shift(5)
        
        return df
    
    def _build_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        构建波动率特征
        
        金融意义：衡量市场波动性和风险
        """
        # 1. ATR 标准化（相对于价格的波动率）
        df['atr_normalized'] = df['atr'] / df['close'] * 100
        
        # 2. 布林带宽度变化
        df['bb_width_change'] = df['bb_width'] - df['bb_width'].shift(5)
        df['bb_width_pct_change'] = df['bb_width'].pct_change(5) * 100
        
        # 3. 历史波动率（多周期标准差）
        df['volatility_5'] = df['close'].pct_change().rolling(5).std() * 100 * np.sqrt(5)
        df['volatility_10'] = df['close'].pct_change().rolling(10).std() * 100 * np.sqrt(10)
        df['volatility_20'] = df['close'].pct_change().rolling(20).std() * 100 * np.sqrt(20)
        
        # 4. 高低点振幅趋势
        df['hl_range_ma5'] = df['high_low_range'].rolling(5).mean()
        df['hl_range_expansion'] = df['high_low_range'] / df['hl_range_ma5']
        
        return df
    
    def _build_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        构建成交量特征
        
        金融意义：衡量市场参与度和资金流向
        """
        # 1. 成交量趋势
        df['volume_trend_5'] = df['volume'].rolling(5).mean() / df['volume_sma']
        df['volume_trend_10'] = df['volume'].rolling(10).mean() / df['volume_sma']
        
        # 2. 成交量变化率
        df['volume_change_pct'] = df['volume'].pct_change() * 100
        df['volume_acceleration'] = df['volume_change_pct'] - df['volume_change_pct'].shift(5)
        
        # 3. 价格-成交量关系（价升量增为正向）
        df['price_volume_trend'] = (
            (df['volume'] * np.sign(df['close'].diff())).rolling(20).sum()
        )
        
        # 4. OBV 趋势
        df['obv_ma20'] = df['obv'].rolling(20).mean()
        df['obv_trend'] = np.where(
            df['obv_ma20'] != 0,
            (df['obv'] - df['obv_ma20']) / abs(df['obv_ma20']) * 100,
            0
        )
        
        # 5. VWAP 偏离趋势
        df['vwap_deviation_ma5'] = df['price_to_vwap_pct'].rolling(5).mean()
        
        return df
    
    def _build_composite_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        构建组合特征
        
        金融意义：多个指标的综合信号
        """
        # 1. 趋势确认分数（-3 到 +3）
        # 综合 EMA、SMA、MACD 的方向
        df['trend_confirmation_score'] = (
            np.sign(df['ema_cross_strength']) +
            np.sign(df['sma_cross_strength']) +
            np.sign(df['macd'])
        )
        
        # 2. 超买超卖综合分数
        # 综合 RSI、布林带位置、价格偏离
        df['overbought_score'] = (
            (df['rsi'] > 70).astype(int) +
            (df['bb_position'] > 80).astype(int) +
            (df['price_to_sma20_pct'] > 5).astype(int)
        )
        df['oversold_score'] = (
            (df['rsi'] < 30).astype(int) +
            (df['bb_position'] < 20).astype(int) +
            (df['price_to_sma20_pct'] < -5).astype(int)
        )
        
        # 3. 市场强度指标
        # 综合趋势强度、成交量、波动率
        df['market_strength'] = (
            abs(df['ema_cross_strength']) * 
            df['volume_ratio'] * 
            (1 + df['atr_normalized'] / 100)
        )
        
        # 4. 风险信号
        # 高波动 + 低流动性 = 高风险
        df['risk_signal'] = (
            df['volatility_20'] * 
            (1 / df['volume_ratio'].replace(0, 1))
        )
        
        # 5. 反转可能性分数
        # RSI极值 + 布林带突破 + MACD背离
        df['reversal_probability'] = (
            ((df['rsi'] > 80) | (df['rsi'] < 20)).astype(int) * 2 +
            ((df['bb_position'] > 95) | (df['bb_position'] < 5)).astype(int) * 2 +
            (df['macd_momentum_5'] * df['macd'] < 0).astype(int)  # MACD 背离
        )
        
        # 6. 趋势持续性分数
        # 趋势方向一致 + 成交量配合 + 波动率适中
        df['trend_sustainability'] = (
            abs(df['trend_confirmation_score']) * 
            np.clip(df['volume_ratio'], 0.5, 2) *
            (1 - np.clip(df['volatility_20'] / 10, 0, 1))  # 波动率过高降低持续性
        )
        
        return df
    
    def get_feature_importance_groups(self) -> Dict[str, List[str]]:
        """
        返回特征的重要性分组
        
        用于：
        1. 特征选择
        2. 模型训练时的特征权重
        3. LLM 上下文构建时的优先级
        """
        return {
            'critical': [  # 核心特征（必须使用）
                'price_to_sma20_pct',
                'ema_cross_strength',
                'macd',
                'rsi',
                'bb_position',
                'trend_confirmation_score',
                'volume_ratio',
                'atr_normalized'
            ],
            'important': [  # 重要特征（建议使用）
                'price_to_sma50_pct',
                'sma_cross_strength',
                'macd_momentum_5',
                'rsi_momentum_5',
                'volatility_20',
                'obv_trend',
                'trend_sustainability',
                'market_strength'
            ],
            'supplementary': [  # 辅助特征（可选）
                'price_slope_20',
                'directional_strength',
                'return_10',
                'bb_width_change',
                'price_volume_trend',
                'overbought_score',
                'oversold_score',
                'reversal_probability'
            ]
        }
    
    def get_feature_descriptions(self) -> Dict[str, str]:
        """
        返回特征的描述（用于文档和 LLM 理解）
        """
        return {
            # 价格位置特征
            'price_to_sma20_pct': '价格相对20日均线的偏离百分比',
            'price_to_sma50_pct': '价格相对50日均线的偏离百分比',
            'bb_position': '价格在布林带中的位置(0-100)',
            'price_to_vwap_pct': '价格相对成交量加权均价的偏离',
            
            # 趋势特征
            'ema_cross_strength': 'EMA12与EMA26的交叉强度',
            'sma_cross_strength': 'SMA20与SMA50的交叉强度',
            'trend_confirmation_score': '多指标趋势确认分数(-3到+3)',
            'trend_sustainability': '趋势持续性评分',
            
            # 动量特征
            'rsi_momentum_5': 'RSI的5期动量',
            'return_10': '10期收益率',
            'momentum_acceleration': '动量加速度',
            
            # 波动率特征
            'atr_normalized': 'ATR标准化（相对价格的波动率）',
            'volatility_20': '20期历史波动率',
            'bb_width_change': '布林带宽度变化',
            
            # 成交量特征
            'volume_ratio': '当前成交量相对均值',
            'obv_trend': 'OBV趋势指标',
            'price_volume_trend': '价格-成交量趋势',
            
            # 组合特征
            'market_strength': '市场强度综合指标',
            'overbought_score': '超买综合评分(0-3)',
            'oversold_score': '超卖综合评分(0-3)',
            'reversal_probability': '反转可能性评分',
            'risk_signal': '风险信号（波动率×流动性倒数）'
        }
