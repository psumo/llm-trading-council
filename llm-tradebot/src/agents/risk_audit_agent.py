"""
👮 风控守护者 (The Guardian) Agent
===========================================

职责:
1. 止损方向自动修正 - 检测并修正做多止损>入场价、做空止损<入场价的致命错误
2. 资金预演 - 模拟订单执行，验证保证金充足、仓位合规
3. 一票否决权 - 高风险决策直接拦截（如已有仓位反向开仓）
4. 物理隔离执行 - 独立运行，不依赖其他Agent状态
5. 审计日志 - 记录所有拦截事件和风控决策

Author: AI Trader Team
Date: 2025-12-19
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from src.utils.logger import log
from src.utils.action_protocol import (
    normalize_action,
    is_open_action,
    is_close_action,
    is_long_action,
    is_short_action,
    is_passive_action,
)


class RiskLevel(Enum):
    """风险等级"""
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"
    FATAL = "fatal"


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    passed: bool  # 是否通过
    risk_level: RiskLevel
    blocked_reason: Optional[str] = None  # 拦截原因（如果未通过）
    corrections: Optional[Dict] = None  # 自动修正内容
    warnings: List[str] = None  # 警告信息


@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    quantity: float
    unrealized_pnl: float
    current_price: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None


class RiskAuditAgent:
    """
    风控守护者 (The Guardian)
    
    核心功能:
    - 止损方向自动修正: 做多止损必须<入场价，做空止损必须>入场价
    - 资金预演: 模拟订单执行，验证保证金充足
    - 一票否决: 拦截高风险决策（如逆向开仓、超杠杆）
    - 物理隔离: 独立运行，不依赖其他Agent
    """
    
    def __init__(
        self, 
        max_leverage: float = 12.0,
        max_position_pct: float = 0.35,  # 最大单仓位占比（35%）
        max_total_risk_pct: float = 0.012,  # 最大总风险敞口（1.2%）
        min_stop_loss_pct: float = 0.002,  # 最小止损距离（0.2%）
        max_stop_loss_pct: float = 0.025,  # 最大止损距离（2.5%）
    ):
        """
        初始化风控守护者 (The Guardian)
        
        Args:
            max_leverage: 最大杠杆倍数
            max_position_pct: 最大单仓位占总资金比例
            max_total_risk_pct: 最大总风险敞口占总资金比例
            min_stop_loss_pct: 最小止损距离（防止s爆）
            max_stop_loss_pct: 最大止损距离（防止过度亏损）
        """
        self.max_leverage = max_leverage
        self.max_position_pct = max_position_pct
        self.max_total_risk_pct = max_total_risk_pct
        self.min_stop_loss_pct = min_stop_loss_pct
        self.max_stop_loss_pct = max_stop_loss_pct
        
        # 审计日志
        self.audit_log: List[Dict] = []
        
        # 拦截统计
        self.block_stats = {
            'total_checks': 0,
            'total_blocks': 0,
            'stop_loss_corrections': 0,
            'reverse_position_blocks': 0,
            'insufficient_margin_blocks': 0,
            'over_leverage_blocks': 0,
        }
        log.info("👮 The Guardian initialized")
    
    async def audit_decision(
        self,
        decision: Dict,
        current_position: Optional[PositionInfo],
        account_balance: float,
        current_price: float,
        atr_pct: float = None  # 新增: ATR 百分比用于动态止损计算
    ) -> RiskCheckResult:
        """
        对决策进行风控审计（主入口）
        
        Args:
            decision: 对抗评论员 (The Critic) 的输出
                {
                    'action': 'long/short/close_long/close_short/hold',
                    'entry_price': 100000.0,
                    'stop_loss': 99000.0,
                    'take_profit': 102000.0,
                    'quantity': 0.01,  # BTC数量
                    'leverage': 5.0,
                    'confidence': 75
                }
            current_position: 当前持仓信息（None表示无仓位）
            account_balance: 账户可用余额（USDT）
            current_price: 当前市场价格
            atr_pct: ATR 百分比 (例如 2.5 表示 2.5%);
                     用于动态计算止损距离，如果未提供则使用默认 2%
            
        Returns:
            RiskCheckResult对象
        """
        self.block_stats['total_checks'] += 1
        warnings = []
        corrections = {}
        
        position_side = current_position.side if current_position else None
        action = normalize_action(decision.get('action', 'wait'), position_side=position_side)
        decision['action'] = action
        is_long = is_long_action(action)
        is_short = is_short_action(action)
        symbol = decision.get('symbol')
        
        # 0. 如果是hold/wait，直接通过
        if is_passive_action(action):
            return RiskCheckResult(
                passed=True,
                risk_level=RiskLevel.SAFE,
                warnings=['观望中']
            )

        if is_open_action(action) and account_balance <= 0:
            return self._block_decision('insufficient_margin_blocks', f"账户余额无效({account_balance:.2f})，无法开仓")

        # 0.1 对抗式数据提取 (Market Awareness)
        regime = decision.get('regime')
        position = decision.get('position')
        confidence = decision.get('confidence', 0)
        if isinstance(confidence, (int, float)) and 0 < confidence <= 1:
            confidence *= 100
        high_confidence = confidence >= 80
        
        # 0.2 市场状态拦截 (Regime Filter)
        if regime:
            r_type = regime.get('regime')
            if r_type == 'unknown':
                if confidence < 55:
                    return self._block_decision('total_blocks', "市场状态不明确，暂停开仓")
                warnings.append("⚠️ 市场状态不明确，谨慎开仓")
            if r_type == 'volatile':
                if confidence < 60:
                    return self._block_decision('total_blocks', f"市场高波动(ATR {regime.get('atr_pct', 0):.2f}%)，风险控制拦截")
                warnings.append(f"⚠️ 市场高波动(ATR {regime.get('atr_pct', 0):.2f}%)，谨慎开仓")
            if r_type == 'choppy':
                if confidence < 60:
                    return self._block_decision('total_blocks', f"震荡市信心不足({confidence:.1f} < 60)，拦截开仓")
                if confidence < 70:
                    warnings.append(f"⚠️ 震荡市信心一般({confidence:.1f} < 70)，谨慎开仓")

        regime_name = str((decision.get('regime') or {}).get('regime', '')).lower()
        trend_scores = decision.get('trend_scores') or {}
        t_1h = trend_scores.get('trend_1h_score')
        t_15m = trend_scores.get('trend_15m_score')
        t_5m = trend_scores.get('trend_5m_score')
        four_layer = decision.get('four_layer') if isinstance(decision.get('four_layer'), dict) else {}
        pos_1h = decision.get('position_1h') if isinstance(decision.get('position_1h'), dict) else None
        sentiment_score = decision.get('sentiment_score')
        symbol_loss_streak = decision.get('symbol_loss_streak', 0)
        symbol_recent_pnl = decision.get('symbol_recent_pnl')
        symbol_recent_trades = decision.get('symbol_recent_trades', 0)
        symbol_long_loss_streak = decision.get('symbol_long_loss_streak', symbol_loss_streak)
        symbol_long_recent_pnl = decision.get('symbol_long_recent_pnl', symbol_recent_pnl)
        symbol_long_recent_trades = decision.get('symbol_long_recent_trades', symbol_recent_trades)
        symbol_short_loss_streak = decision.get('symbol_short_loss_streak', symbol_loss_streak)
        symbol_short_recent_pnl = decision.get('symbol_short_recent_pnl', symbol_recent_pnl)
        symbol_short_recent_trades = decision.get('symbol_short_recent_trades', symbol_recent_trades)
        continuation_guard = self._allow_continuation_guard(
            action=action,
            confidence=confidence,
            trend_scores=trend_scores,
            regime_name=regime_name,
            four_layer=four_layer
        )
        if continuation_guard:
            warnings.append("⚡ 强趋势延续信号已确认：部分风控阈值放宽")

        # 0.15 1h位置方向硬拦截 (Hard Veto)
        if is_open_action(action) and pos_1h:
            allow_long = pos_1h.get('allow_long')
            allow_short = pos_1h.get('allow_short')
            pos_pct = pos_1h.get('position_pct')
            location = pos_1h.get('location', 'unknown')
            pos_desc = f"1h位置={location}"
            if isinstance(pos_pct, (int, float)):
                pos_desc = f"{pos_desc}({pos_pct:.1f}%)"

            if is_long and allow_long is False:
                if self._allow_position_override(
                    action=action,
                    confidence=confidence,
                    trend_scores=trend_scores,
                    regime_name=regime_name,
                    position_1h=pos_1h
                ):
                    warnings.append(f"⚠️ 1h方向过滤触发突破放行: {pos_desc} (long breakout override)")
                else:
                    return self._block_decision(
                        'total_blocks',
                        f"1h方向过滤拦截: 当前{pos_desc}禁止做多(allow_long=False)"
                    )
            if is_short and allow_short is False:
                if self._allow_position_override(
                    action=action,
                    confidence=confidence,
                    trend_scores=trend_scores,
                    regime_name=regime_name,
                    position_1h=pos_1h
                ):
                    warnings.append(f"⚠️ 1h方向过滤触发突破放行: {pos_desc} (short breakdown override)")
                else:
                    return self._block_decision(
                        'total_blocks',
                        f"1h方向过滤拦截: 当前{pos_desc}禁止做空(allow_short=False)"
                    )

        # 0.16 震荡市多周期冲突拦截 (Conflict Veto)
        if is_open_action(action) and self._is_sideways_regime(regime_name):
            trend_points = {
                '1h': t_1h,
                '15m': t_15m,
                '5m': t_5m
            }
            bullish = {tf: score for tf, score in trend_points.items() if isinstance(score, (int, float)) and score >= 15}
            bearish = {tf: score for tf, score in trend_points.items() if isinstance(score, (int, float)) and score <= -15}
            if bullish and bearish:
                bullish_txt = ", ".join(f"{tf}:{v:+.0f}" for tf, v in bullish.items())
                bearish_txt = ", ".join(f"{tf}:{v:+.0f}" for tf, v in bearish.items())
                if confidence < 85:
                    return self._block_decision(
                        'total_blocks',
                        f"震荡市多周期趋势冲突(bull=[{bullish_txt}] vs bear=[{bearish_txt}])，禁止开仓"
                    )
                warnings.append(
                    f"⚠️ 震荡市多周期趋势冲突(bull=[{bullish_txt}] vs bear=[{bearish_txt}])，仅因高信心放行"
                )

            if is_long and isinstance(t_1h, (int, float)) and t_1h <= -35 and confidence < 90:
                return self._block_decision(
                    'total_blocks',
                    f"震荡市1h空头趋势明显(1h={t_1h:+.0f})，拦截逆向做多"
                )
            if is_short and isinstance(t_1h, (int, float)) and t_1h >= 35 and confidence < 90:
                return self._block_decision(
                    'total_blocks',
                    f"震荡市1h多头趋势明显(1h={t_1h:+.0f})，拦截逆向做空"
                )

        osc_scores = decision.get('oscillator_scores') or decision.get('oscillator') or {}
        osc_values = [
            osc_scores.get('osc_1h_score'),
            osc_scores.get('osc_15m_score'),
            osc_scores.get('osc_5m_score')
        ]
        osc_values = [v for v in osc_values if isinstance(v, (int, float))]
        osc_min = min(osc_values) if osc_values else None
        long_strong_setup = False
        if is_long and osc_min is not None:
            if isinstance(t_5m, (int, float)) and isinstance(t_15m, (int, float)):
                if t_5m >= 20 and t_15m >= 15 and osc_min > -30:
                    long_strong_setup = True
            if not long_strong_setup and isinstance(t_1h, (int, float)) and isinstance(t_15m, (int, float)):
                if t_1h >= 50 and t_15m >= 15 and osc_min > -25 and 'downtrend' not in regime_name:
                    long_strong_setup = True
        short_strong_setup = False
        if is_short and osc_min is not None:
            if isinstance(t_5m, (int, float)) and isinstance(t_15m, (int, float)):
                if t_5m <= -20 and t_15m <= -15 and osc_min <= -30:
                    short_strong_setup = True
            if not short_strong_setup and isinstance(t_1h, (int, float)) and isinstance(t_15m, (int, float)):
                if t_1h <= -50 and t_15m <= -15 and osc_min <= -30 and 'uptrend' not in regime_name:
                    short_strong_setup = True
        short_confidence = confidence >= 55

        if is_long and isinstance(symbol_long_loss_streak, (int, float)) and symbol_long_loss_streak >= 2:
            if confidence < 80 and not long_strong_setup:
                return self._block_decision('total_blocks', f"{symbol}多头连续亏损{int(symbol_long_loss_streak)}次，触发冷却")
            warnings.append(f"⚠️ {symbol}多头连续亏损{int(symbol_long_loss_streak)}次，谨慎做多")
        if is_long and isinstance(symbol_long_recent_pnl, (int, float)) and symbol_long_recent_trades >= 3:
            long_loss_threshold = -max(2.0, account_balance * 0.003)
            if symbol_long_recent_pnl <= long_loss_threshold and confidence < 80 and not long_strong_setup:
                return self._block_decision(
                    'total_blocks',
                    f"{symbol}多头近{symbol_long_recent_trades}单净亏损{symbol_long_recent_pnl:.2f}，暂停多单"
                )
            if symbol_long_recent_pnl < 0:
                warnings.append(f"⚠️ {symbol}多头近{symbol_long_recent_trades}单净亏损{symbol_long_recent_pnl:.2f}")

        if is_short and not short_confidence:
            if not continuation_guard or confidence < 52:
                return self._block_decision('total_blocks', f"空头信心不足({confidence:.1f} < 55)，拦截做空")
            warnings.append(f"⚠️ 空头信心略低({confidence:.1f})，因延续信号放宽")
        if is_short and not short_strong_setup:
            if confidence < 65 and not continuation_guard:
                return self._block_decision('total_blocks', "空头信号未达到强共振条件，拦截做空")
            warnings.append("⚠️ 空头共振偏弱，谨慎做空")
        if is_short and isinstance(symbol_short_loss_streak, (int, float)) and symbol_short_loss_streak >= 2:
            if confidence < 80 and not short_strong_setup:
                return self._block_decision('total_blocks', f"{symbol}空头连续亏损{int(symbol_short_loss_streak)}次，触发冷却")
            warnings.append(f"⚠️ {symbol}空头连续亏损{int(symbol_short_loss_streak)}次，谨慎做空")
        if is_short and isinstance(symbol_short_recent_pnl, (int, float)) and symbol_short_recent_trades >= 3:
            loss_threshold = -max(2.0, account_balance * 0.003)
            if symbol_short_recent_pnl <= loss_threshold and confidence < 80 and not continuation_guard:
                return self._block_decision('total_blocks', f"{symbol}空头近{symbol_short_recent_trades}单净亏损{symbol_short_recent_pnl:.2f}，暂停空单")
            if symbol_short_recent_pnl < 0:
                warnings.append(f"⚠️ {symbol}空头近{symbol_short_recent_trades}单净亏损{symbol_short_recent_pnl:.2f}")
        if is_short and regime_name == 'volatile_directionless' and not short_strong_setup:
            if confidence < 70 and not continuation_guard:
                return self._block_decision('total_blocks', "震荡无方向区间，空头需更高信心")
            if isinstance(t_1h, (int, float)) and t_1h > -45 and not continuation_guard:
                return self._block_decision('total_blocks', f"震荡无方向区间，空头趋势不足(1h={t_1h:+.0f})")
            if osc_min is not None and osc_min > -20 and not continuation_guard:
                return self._block_decision('total_blocks', f"震荡无方向区间，空头超买不足(最弱:{osc_min:+.0f})")
            warnings.append("⚠️ 震荡无方向区间空头风险偏高")
        if is_short and isinstance(sentiment_score, (int, float)) and sentiment_score > 20:
            if confidence < 80 and not short_strong_setup and not continuation_guard:
                return self._block_decision('total_blocks', f"市场情绪偏多({sentiment_score:+.0f})，空头拦截")
            warnings.append(f"⚠️ 市场情绪偏多({sentiment_score:+.0f})，谨慎做空")
        if is_short and isinstance(atr_pct, (int, float)) and atr_pct > 3.0 and confidence < 75 and not continuation_guard:
            return self._block_decision('total_blocks', f"高波动空头风险过高(ATR {atr_pct:.2f}%)")
        # 🔧 OPTIMIZATION: Relax symbol-specific filters (was blocking all trades)
        # Changed from hard blocks to conditional warnings
        symbol_upper = str(symbol).upper() if symbol else ""
        
        # FILUSDT: Discourage SHORT but allow with high confidence
        if symbol_upper == "FILUSDT":
            if is_short and confidence < 70 and not continuation_guard:
                return self._block_decision('total_blocks', "FILUSDT做空需高信心(≥70%)")
            elif is_short:
                warnings.append("⚠️ FILUSDT做空风险较高，谨慎操作")
        
        # FETUSDT: Similar relaxation
        if symbol_upper == "FETUSDT":
            if is_short and confidence < 70 and not continuation_guard:
                return self._block_decision('total_blocks', "FETUSDT做空需高信心(≥70%)")
        
        # 🔧 OPTIMIZATION: Relax LINKUSDT/FILUSDT LONG requirements
        # Changed from 85% confidence requirement to 75%
        strict_long_symbols = {"FILUSDT", "LINKUSDT"}
        if is_long and symbol_upper in strict_long_symbols:
            if not long_strong_setup and confidence < 60:  # Phase 3: 75 -> 60
                return self._block_decision(
                    'total_blocks',
                    f"{symbol_upper}做多需强信号或高信心(≥60%)"
                )
            elif confidence < 60:
                warnings.append(f"⚠️ {symbol_upper}做多信心偏低({confidence:.1f}% < 60%)")

        # 0.3 价格位置拦截 (Position Filter)
        if position:
            pos_pct = position.get('position_pct', 50)
            location = position.get('location')
            pos_1h = decision.get('position_1h') if isinstance(decision.get('position_1h'), dict) else None
            short_pos_pct = pos_pct
            if pos_1h and isinstance(pos_1h.get('position_pct'), (int, float)):
                short_pos_pct = pos_1h.get('position_pct', pos_pct)
            short_pos_threshold = 65 if not short_strong_setup else 55

            if location == 'middle' or 40 <= pos_pct <= 60:
                if not ((is_short and short_strong_setup and short_pos_pct >= short_pos_threshold) or (is_long and long_strong_setup)):
                    if confidence < 55:
                        return self._block_decision('total_blocks', f"价格处于区间中部({pos_pct:.1f}%)，R/R极差，禁止开仓")
                    warnings.append(f"⚠️ 价格处于区间中部({pos_pct:.1f}%)，R/R偏弱，谨慎开仓")
            
            if is_long and pos_pct > 70:
                if pos_pct > 80 and confidence < 55 and not long_strong_setup:
                    return self._block_decision('total_blocks', f"做多位置过高({pos_pct:.1f}%)，存在回调风险")
                warnings.append(f"⚠️ 做多位置偏高({pos_pct:.1f}%)，谨慎开仓")
            
            if is_short and short_pos_pct < short_pos_threshold:
                if confidence < 70 and not short_strong_setup and not continuation_guard:
                    return self._block_decision('total_blocks', f"做空位置偏低({short_pos_pct:.1f}%)，需接近1h阻力带(≥{short_pos_threshold:.0f}%)")
                warnings.append(f"⚠️ 做空位置偏低({short_pos_pct:.1f}%)，谨慎开仓")

        # 0.35 方向不明时的做多收紧 (Volatile Directionless Guard)
        if regime_name == 'volatile_directionless' and is_long and not long_strong_setup:
            if confidence < 70:
                return self._block_decision('total_blocks', "方向不明(volatile_directionless)，做多需更强趋势确认")
            warnings.append("⚠️ 方向不明(volatile_directionless)，谨慎做多")

        # 0.5 震荡指标冲突拦截 (Overbought/Oversold Guard)
        osc_scores = decision.get('oscillator_scores') or decision.get('oscillator') or {}
        osc_values = [
            osc_scores.get('osc_1h_score'),
            osc_scores.get('osc_15m_score'),
            osc_scores.get('osc_5m_score')
        ]
        osc_values = [v for v in osc_values if isinstance(v, (int, float))]
        if osc_values:
            osc_min = min(osc_values)
            osc_max = max(osc_values)
            if is_long and osc_min <= -70:
                return self._block_decision('total_blocks', f"震荡指标强烈超买({osc_min:.0f})，避免追高做多")
            if is_short and osc_max >= 50:
                return self._block_decision('total_blocks', f"震荡指标强烈超卖({osc_max:.0f})，避免追低做空")
            if is_short and osc_min > -15:
                if confidence < 70 and not continuation_guard:
                    return self._block_decision('total_blocks', f"空头缺乏超买信号(最弱:{osc_min:+.0f})，避免弱势做空")
                warnings.append(f"⚠️ 空头超买信号偏弱(最弱:{osc_min:+.0f})")

        # 0.6 空头趋势强度过滤 (Backtest 优化: 空头全败 -> 提高门槛)
        trend_scores = decision.get('trend_scores') or {}
        t_1h = trend_scores.get('trend_1h_score')
        t_15m = trend_scores.get('trend_15m_score')
        if is_short:
            # 若缺少趋势分数，则跳过此规则
            if isinstance(t_1h, (int, float)) and t_1h > -50:
                if confidence < 70 and not continuation_guard:
                    return self._block_decision('total_blocks', f"空头趋势不足(1h={t_1h:+.0f})，避免逆势做空")
                warnings.append(f"⚠️ 空头趋势偏弱(1h={t_1h:+.0f})，谨慎做空")
            if isinstance(t_15m, (int, float)) and t_15m > -15:
                if confidence < 70 and not continuation_guard:
                    return self._block_decision('total_blocks', f"空头趋势不足(15m={t_15m:+.0f})，避免逆势做空")
                warnings.append(f"⚠️ 空头趋势偏弱(15m={t_15m:+.0f})，谨慎做空")
            # Regime 反向过滤 (仅在可识别趋势时启用)
            regime = decision.get('regime') or {}
            regime_name = str(regime.get('regime', '')).lower()
            if regime_name in ['trending_up'] or 'uptrend' in regime_name:
                if confidence < 70 and not continuation_guard:
                    return self._block_decision('total_blocks', f"趋势向上({regime.get('regime')}), 禁止逆势做空")
                warnings.append(f"⚠️ 趋势向上({regime.get('regime')}), 谨慎做空")

        # 0.4 盈亏比硬核检查 (R/R Ratio)
        entry_price = decision.get('entry_price', current_price)
        stop_loss = decision.get('stop_loss')
        take_profit = decision.get('take_profit')
        if entry_price and stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < 1.15:
                    return self._block_decision('total_blocks', f"风险回报比不足({rr_ratio:.2f} < 1.15)")
        
        # 1. 【一票否决】检查逆向开仓
        if current_position:
            # 1.1 检查重复开仓 (Duplicate Open Block)
            duplicated_check = self._check_duplicate_open(action, current_position)
            if not duplicated_check['passed']:
                return self._block_decision(
                    'total_blocks',
                    duplicated_check['reason']
                )
            
            # 1.2 检查逆向开仓
            reverse_check = self._check_reverse_position(action, current_position)
            if not reverse_check['passed']:
                return self._block_decision(
                    'reverse_position_blocks',
                    reverse_check['reason']
                )
        
        # 2. 【致命修正】止损方向检查
        if is_open_action(action):
            stop_loss_check = self._check_and_fix_stop_loss(
                action=action,
                entry_price=decision.get('entry_price', current_price),
                stop_loss=decision.get('stop_loss'),
                current_price=current_price,
                atr_pct=atr_pct  # 传递 ATR 用于动态计算
            )
            
            if not stop_loss_check['passed']:
                if stop_loss_check['can_fix']:
                    # 自动修正
                    corrections['stop_loss'] = stop_loss_check['corrected_value']
                    warnings.append(f"⚠️ 止损方向错误已修正: {decision.get('stop_loss')} -> {stop_loss_check['corrected_value']}")
                    self.block_stats['stop_loss_corrections'] += 1
                else:
                    # 无法修正，拦截
                    return self._block_decision(
                        'stop_loss_corrections',
                        stop_loss_check['reason']
                    )
        
        # 3. 【资金预演】保证金检查
        margin_check = self._check_margin_sufficiency(
            action=action,
            entry_price=decision.get('entry_price', current_price),
            quantity=decision.get('quantity', 0),
            leverage=decision.get('leverage', 1.0),
            account_balance=account_balance
        )
        
        if not margin_check['passed']:
            return self._block_decision(
                'insufficient_margin_blocks',
                margin_check['reason']
            )
        
        # 4. 【杠杆检查】防止过度杠杆
        leverage = decision.get('leverage', 1.0)
        if leverage > self.max_leverage:
            return self._block_decision(
                'over_leverage_blocks',
                f"杠杆{leverage}x超过最大限制{self.max_leverage}x"
            )
        
        # 5. 【仓位检查】单仓位占比
        position_check = self._check_position_size(
            quantity=decision.get('quantity', 0),
            entry_price=decision.get('entry_price', current_price),
            account_balance=account_balance
        )
        
        if not position_check['passed']:
            warnings.append(f"⚠️ {position_check['reason']}")
        
        # 6. 【风险敞口】总风险检查
        risk_check = self._check_total_risk_exposure(
            action=action,
            entry_price=decision.get('entry_price', current_price),
            stop_loss=corrections.get('stop_loss', decision.get('stop_loss')),
            quantity=decision.get('quantity', 0),
            account_balance=account_balance
        )
        
        if not risk_check['passed']:
            warnings.append(f"⚠️ {risk_check['reason']}")

        # 6.5 【陷阱审计】用户经验风控 (Trap & Pattern)
        trap_check = self._check_market_traps_risk(decision)
        if not trap_check['passed']:
            # 陷阱检测可能会直接拦截（如诱多风险）
             return self._block_decision(
                'total_blocks',
                trap_check['reason']
            )
        if trap_check.get('warnings'):
            warnings.extend(trap_check['warnings'])
        
        # 7. 综合评估风险等级
        risk_level = self._evaluate_risk_level(
            len(warnings),
            confidence,
            leverage
        )
        
        # 8. 记录审计日志
        # log.guardian(f"审计通过: {action.upper()} (信心: {confidence:.1f}%)")
        self._log_audit(
            decision=decision,
            result='PASSED',
            corrections=corrections,
            warnings=warnings
        )
        
        return RiskCheckResult(
            passed=True,
            risk_level=risk_level,
            corrections=corrections if corrections else None,
            warnings=warnings if warnings else None
        )

    def _allow_continuation_guard(
        self,
        *,
        action: str,
        confidence: float,
        trend_scores: Dict,
        regime_name: str,
        four_layer: Dict
    ) -> bool:
        """Allow limited guard relaxation when four-layer confirms strong continuation."""
        if not is_open_action(action):
            return False
        if not isinstance(four_layer, dict):
            return False
        if not all(bool(four_layer.get(k)) for k in ('layer1_pass', 'layer2_pass', 'layer3_pass', 'layer4_pass')):
            return False
        if self._is_sideways_regime(regime_name):
            return False
        if confidence < 58:
            return False

        final_action = str(four_layer.get('final_action', '') or '').lower()
        expected = 'short' if is_short_action(action) else 'long'
        if final_action != expected:
            return False

        adx = four_layer.get('adx')
        if not isinstance(adx, (int, float)) or adx < 24:
            return False

        trigger_pattern = str(four_layer.get('trigger_pattern', '') or '').lower()
        if trigger_pattern not in {'breakout', 'engulfing', 'rvol_momentum', 'soft_momentum'}:
            return False

        t_1h = trend_scores.get('trend_1h_score') if isinstance(trend_scores, dict) else None
        t_15m = trend_scores.get('trend_15m_score') if isinstance(trend_scores, dict) else None
        if not isinstance(t_1h, (int, float)) or not isinstance(t_15m, (int, float)):
            return False

        if expected == 'short':
            return t_1h <= -45 and t_15m <= -15
        return t_1h >= 45 and t_15m >= 15

    def _is_sideways_regime(self, regime_name: str) -> bool:
        """Whether the regime description indicates consolidation/range state."""
        name = str(regime_name or '').lower()
        if not name:
            return False
        return any(keyword in name for keyword in ('sideways', 'consolidation', 'choppy', 'range', 'directionless'))

    def _allow_position_override(
        self,
        *,
        action: str,
        confidence: float,
        trend_scores: Dict,
        regime_name: str,
        position_1h: Dict
    ) -> bool:
        """Allow rare breakout override when 1h range filter disagrees with strong trend breakout."""
        if self._is_sideways_regime(regime_name):
            return False
        if confidence < 92:
            return False
        if not isinstance(position_1h, dict):
            return False

        location = str(position_1h.get('location', '')).lower()
        pos_pct = position_1h.get('position_pct')
        if not isinstance(pos_pct, (int, float)):
            return False

        t_1h = trend_scores.get('trend_1h_score') if isinstance(trend_scores, dict) else None
        t_15m = trend_scores.get('trend_15m_score') if isinstance(trend_scores, dict) else None
        t_5m = trend_scores.get('trend_5m_score') if isinstance(trend_scores, dict) else None
        if not all(isinstance(v, (int, float)) for v in (t_1h, t_15m, t_5m)):
            return False

        if action == 'open_long':
            return (
                location in {'upper', 'resistance'}
                and pos_pct >= 70
                and t_1h >= 55
                and t_15m >= 25
                and t_5m >= 10
            )
        if action == 'open_short':
            return (
                location in {'support', 'lower'}
                and pos_pct <= 30
                and t_1h <= -55
                and t_15m <= -25
                and t_5m <= -10
            )
        return False
    
    
    def _check_duplicate_open(
        self,
        action: str,
        current_position: PositionInfo
    ) -> Dict:
        """
        检查是否重复开仓 (Single Position Rule)
        
        规则: 同一个symbol如果已经持有仓位，禁止再次开仓 (long/short)。
        只允许 close/add/reduce 相关操作 (目前仅支持单一仓位，所以add暂不支持或需特殊处理)
        """
        if is_open_action(action):
            # 只要是开仓动作，且当前有仓位 -> 拦截
            return {
                'passed': False,
                'reason': f"【单一持仓限制】当前持有{current_position.side}仓位，禁止重复开{action}"
            }
        
        return {'passed': True}
    
    def _check_reverse_position(
        self, 
        action: str, 
        current_position: PositionInfo
    ) -> Dict:
        """
        检查是否尝试逆向开仓（致命错误）
        
        例如: 已有多单，又尝试开空单
        """
        if is_long_action(action) and current_position.side == 'short':
            return {
                'passed': False,
                'reason': f"【致命风险】持有{current_position.side}仓位时禁止开{action}仓"
            }
        
        if is_short_action(action) and current_position.side == 'long':
            return {
                'passed': False,
                'reason': f"【致命风险】持有{current_position.side}仓位时禁止开{action}仓"
            }
        
        return {'passed': True}
    
    def _check_and_fix_stop_loss(
        self,
        action: str,
        entry_price: float,
        stop_loss: Optional[float],
        current_price: float,
        atr_pct: float = None  # 新增 ATR 参数
    ) -> Dict:
        """
        检查并修正止损方向（核心功能 - ATR 增强版）
        
        规则:
        - 做多(long): 止损必须 < 入场价
        - 做空(short): 止损必须 > 入场价
        
        ATR 动态计算:
        - 如果提供了 atr_pct，使用 1.5 * ATR 作为止损距离
        - 保留最小/最大止损限制作为边界
        
        Returns:
            {
                'passed': bool,
                'can_fix': bool,
                'corrected_value': float,
                'reason': str
            }
        """
        # 计算动态止损距离
        # 优先级: ATR -> 默认 2%
        if atr_pct and atr_pct > 0:
            # 使用 1.5 * ATR 作为止损距离（常见策略）
            dynamic_stop_pct = min(max(atr_pct * 1.5 / 100, self.min_stop_loss_pct), self.max_stop_loss_pct)
            log.debug(f"📊 ATR-based stop: ATR={atr_pct:.2f}%, dynamic_stop={dynamic_stop_pct:.2%}")
        else:
            # 无 ATR 数据，使用默认 1%
            dynamic_stop_pct = 0.01
        
        if not stop_loss:
            # 没有设置止损，使用动态止损距离
            if is_long_action(action):
                default_stop = entry_price * (1 - dynamic_stop_pct)
            else:
                default_stop = entry_price * (1 + dynamic_stop_pct)
            return {
                'passed': False,
                'can_fix': True,
                'corrected_value': default_stop,
                'reason': f"未设置止损，使用动态止损(ATR-based {dynamic_stop_pct:.1%}): {default_stop:.2f}"
            }
        
        # 做多检查
        if is_long_action(action):
            if stop_loss >= entry_price:
                # 止损方向错误，使用动态止损修正
                corrected = entry_price * (1 - dynamic_stop_pct)
                return {
                    'passed': False,
                    'can_fix': True,
                    'corrected_value': corrected,
                    'reason': f"做多止损{stop_loss}≥入场价{entry_price}，使用ATR修正为{corrected:.2f}"
                }
            
            # 检查止损距离是否合理
            stop_distance_pct = abs(entry_price - stop_loss) / entry_price
            if stop_distance_pct < self.min_stop_loss_pct:
                corrected = entry_price * (1 - max(dynamic_stop_pct, self.min_stop_loss_pct))
                return {
                    'passed': False,
                    'can_fix': True,
                    'corrected_value': corrected,
                    'reason': f"止损距离过小({stop_distance_pct:.2%})，已调整为{max(dynamic_stop_pct, self.min_stop_loss_pct):.2%}"
                }
            
            if stop_distance_pct > self.max_stop_loss_pct:
                corrected = entry_price * (1 - self.max_stop_loss_pct)
                return {
                    'passed': False,
                    'can_fix': True,
                    'corrected_value': corrected,
                    'reason': f"止损距离过大({stop_distance_pct:.2%})，已调整为{self.max_stop_loss_pct:.2%}"
                }
        
        # 做空检查
        if is_short_action(action):
            if stop_loss <= entry_price:
                # 止损方向错误，使用动态止损修正
                corrected = entry_price * (1 + dynamic_stop_pct)
                return {
                    'passed': False,
                    'can_fix': True,
                    'corrected_value': corrected,
                    'reason': f"做空止损{stop_loss}≤入场价{entry_price}，使用ATR修正为{corrected:.2f}"
                }
            
            # 检查止损距离
            stop_distance_pct = abs(stop_loss - entry_price) / entry_price
            if stop_distance_pct < self.min_stop_loss_pct:
                corrected = entry_price * (1 + max(dynamic_stop_pct, self.min_stop_loss_pct))
                return {
                    'passed': False,
                    'can_fix': True,
                    'corrected_value': corrected,
                    'reason': f"止损距离过小({stop_distance_pct:.2%})，已调整为{max(dynamic_stop_pct, self.min_stop_loss_pct):.2%}"
                }
            
            if stop_distance_pct > self.max_stop_loss_pct:
                corrected = entry_price * (1 + self.max_stop_loss_pct)
                return {
                    'passed': False,
                    'can_fix': True,
                    'corrected_value': corrected,
                    'reason': f"止损距离过大({stop_distance_pct:.2%})，已调整为{self.max_stop_loss_pct:.2%}"
                }
        
        return {'passed': True}
    
    def _check_margin_sufficiency(
        self,
        action: str,
        entry_price: float,
        quantity: float,
        leverage: float,
        account_balance: float
    ) -> Dict:
        """
        资金预演: 检查保证金是否充足
        
        计算公式:
        所需保证金 = (数量 * 入场价) / 杠杆
        """
        if is_close_action(action) or is_passive_action(action):
            return {'passed': True}
        
        required_margin = (quantity * entry_price) / leverage
        
        # 预留5%缓冲
        if required_margin > account_balance * 0.95:
            return {
                'passed': False,
                'reason': f"保证金不足: 需要{required_margin:.2f} USDT，可用{account_balance:.2f} USDT"
            }
        
        return {'passed': True, 'required_margin': required_margin}
    
    def _check_position_size(
        self,
        quantity: float,
        entry_price: float,
        account_balance: float
    ) -> Dict:
        """
        检查单仓位占比是否超标
        
        仓位价值 = 数量 * 价格
        占比 = 仓位价值 / 账户余额
        """
        if account_balance <= 0:
            return {
                'passed': False,
                'reason': "账户余额无效(<=0)，无法计算仓位占比"
            }

        position_value = quantity * entry_price
        position_pct = position_value / account_balance
        
        if position_pct > self.max_position_pct:
            return {
                'passed': False,
                'reason': f"单仓位占比{position_pct:.2%}超过限制{self.max_position_pct:.2%}"
            }
        
        return {'passed': True}
    
    def _check_total_risk_exposure(
        self,
        action: str,
        entry_price: float,
        stop_loss: Optional[float],
        quantity: float,
        account_balance: float
    ) -> Dict:
        """
        检查总风险敞口（最大可能亏损）
        
        风险敞口 = |入场价 - 止损价| * 数量
        风险占比 = 风险敞口 / 账户余额
        """
        if not stop_loss or is_close_action(action) or is_passive_action(action):
            return {'passed': True}

        if account_balance <= 0:
            return {
                'passed': False,
                'reason': "账户余额无效(<=0)，无法计算风险敞口"
            }
        
        risk_exposure = abs(entry_price - stop_loss) * quantity
        risk_pct = risk_exposure / account_balance
        
        if risk_pct > self.max_total_risk_pct:
            return {
                'passed': False,
                'reason': f"风险敞口{risk_pct:.2%}超过限制{self.max_total_risk_pct:.2%}"
            }
        
        return {'passed': True}
    
    def _check_market_traps_risk(self, decision: Dict) -> Dict:
        """
        检查市场陷阱风险 (User Experience Logic)
        
        基于用户的10年经验：
        1. 涨得快跌得慢 -> 诱多，拦截做多
        2. 暴跌后弱反弹 -> 诱多，拦截做多
        3. 高位无量 -> 诱多，拦截做多
        """
        traps = decision.get('traps') or {}
        action = normalize_action(decision.get('action', 'wait'))
        
        if not is_long_action(action):
            return {'passed': True}
            
        # 1. 诱多风险 (Rapid Rise, Slow Fall)
        if traps.get('bull_trap_risk'):
            return {
                'passed': False,
                'reason': "【用户经验风控】识别到'急涨缓跌'诱多形态，禁止做多"
            }
            
        # 2. 弱反弹 (Weak Rebound)
        if traps.get('weak_rebound'):
            # 弱反弹不一定全拦，但如果是高杠杆或者低信心，则拦截
            confidence = decision.get('confidence', 0)
            if confidence < 60:  # Phase 3: 75 -> 60
                return {
                    'passed': False,
                    'reason': f"【用户经验风控】弱反弹(缩量)信心不足({confidence:.1f})，禁止做多"
                }
            return { # 只是警告
                'passed': True,
                'warnings': ["⚠️ 弱反弹警示：暴跌后无量反弹，谨防假突破"]
            }
            
        # 3. 高位无量 (Volume Divergence)
        if traps.get('volume_divergence'):
            # 高位无量非常危险
            return {
                'passed': False,
                'reason': "【用户经验风控】高位缩量(量价背离)，庄家可能出货，禁止做多"
            }
            
        return {'passed': True}

    def _evaluate_risk_level(
        self,
        warning_count: int,
        confidence: float,
        leverage: float
    ) -> RiskLevel:
        """综合评估风险等级"""
        if warning_count >= 3 or leverage > 8:
            return RiskLevel.DANGER
        elif warning_count >= 1 or leverage > 5:
            return RiskLevel.WARNING
        elif confidence > 70:
            return RiskLevel.SAFE
        else:
            return RiskLevel.WARNING
    
    def _block_decision(self, stat_key: str, reason: str) -> RiskCheckResult:
        """拦截决策并记录"""
        self.block_stats['total_blocks'] += 1
        self.block_stats[stat_key] += 1
        
        # log.guardian(f"决策拦截: {reason}", blocked=True)
        
        self._log_audit(
            decision={'blocked': True},
            result='BLOCKED',
            corrections=None,
            warnings=[reason]
        )
        
        return RiskCheckResult(
            passed=False,
            risk_level=RiskLevel.FATAL,
            blocked_reason=reason
        )
    
    def _log_audit(
        self,
        decision: Dict,
        result: str,
        corrections: Optional[Dict],
        warnings: List[str]
    ):
        """记录审计日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'decision': decision,
            'result': result,
            'corrections': corrections,
            'warnings': warnings,
        }
        self.audit_log.append(log_entry)
        
        # 保留最近1000条记录
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]
    
    def get_audit_report(self) -> Dict:
        """生成审计报告"""
        return {
            'total_checks': self.block_stats['total_checks'],
            'total_blocks': self.block_stats['total_blocks'],
            'block_rate': (
                self.block_stats['total_blocks'] / self.block_stats['total_checks']
                if self.block_stats['total_checks'] > 0 else 0
            ),
            'block_breakdown': {
                'stop_loss_corrections': self.block_stats['stop_loss_corrections'],
                'reverse_position_blocks': self.block_stats['reverse_position_blocks'],
                'insufficient_margin_blocks': self.block_stats['insufficient_margin_blocks'],
                'over_leverage_blocks': self.block_stats['over_leverage_blocks'],
            },
            'recent_logs': self.audit_log[-10:]  # 最近10条日志
        }


# ============================================
# 测试函数
# ============================================
async def test_risk_audit():
    """测试风控审计官Agent"""
    print("\n" + "="*60)
    print("🧪 测试风控审计官Agent")
    print("="*60)
    
    # 初始化
    risk_agent = RiskAuditAgent(
        max_leverage=10.0,
        max_position_pct=0.3,
        min_stop_loss_pct=0.005,
        max_stop_loss_pct=0.05
    )
    
    # 测试1: 止损方向错误修正（做多）
    print("\n1️⃣ 测试做多止损方向修正...")
    decision_1 = {
        'action': 'long',
        'entry_price': 100000.0,
        'stop_loss': 100500.0,  # ❌ 错误: 做多止损>入场价
        'quantity': 0.01,
        'leverage': 5.0,
        'confidence': 75
    }
    
    result_1 = await risk_agent.audit_decision(
        decision=decision_1,
        current_position=None,
        account_balance=10000.0,
        current_price=100000.0
    )
    
    print(f"  结果: {'✅ 通过' if result_1.passed else '❌ 拦截'}")
    if result_1.warnings:
        for w in result_1.warnings:
            print(f"  {w}")
    
    # 测试2: 止损方向错误修正（做空）
    print("\n2️⃣ 测试做空止损方向修正...")
    decision_2 = {
        'action': 'short',
        'entry_price': 100000.0,
        'stop_loss': 99500.0,  # ❌ 错误: 做空止损<入场价
        'quantity': 0.01,
        'leverage': 5.0,
        'confidence': 75
    }
    
    result_2 = await risk_agent.audit_decision(
        decision=decision_2,
        current_position=None,
        account_balance=10000.0,
        current_price=100000.0
    )
    
    print(f"  结果: {'✅ 通过' if result_2.passed else '❌ 拦截'}")
    if result_2.corrections:
        print(f"  修正: {result_2.corrections}")
    
    # 测试3: 逆向开仓拦截
    print("\n3️⃣ 测试逆向开仓拦截...")
    current_pos = PositionInfo(
        symbol='BTCUSDT',
        side='long',
        entry_price=99000.0,
        quantity=0.01,
        unrealized_pnl=100.0
    )
    
    decision_3 = {
        'action': 'short',  # ❌ 错误: 已有多单还要开空单
        'entry_price': 100000.0,
        'stop_loss': 101000.0,
        'quantity': 0.01,
        'leverage': 5.0,
        'confidence': 75
    }
    
    result_3 = await risk_agent.audit_decision(
        decision=decision_3,
        current_position=current_pos,
        account_balance=10000.0,
        current_price=100000.0
    )
    
    print(f"  结果: {'✅ 通过' if result_3.passed else '❌ 拦截'}")
    if result_3.blocked_reason:
        print(f"  拦截原因: {result_3.blocked_reason}")
    
    # 测试4: 保证金不足拦截
    print("\n4️⃣ 测试保证金不足拦截...")
    decision_4 = {
        'action': 'long',
        'entry_price': 100000.0,
        'stop_loss': 98000.0,
        'quantity': 0.5,  # ❌ 数量过大，保证金不足
        'leverage': 2.0,
        'confidence': 75
    }
    
    result_4 = await risk_agent.audit_decision(
        decision=decision_4,
        current_position=None,
        account_balance=10000.0,
        current_price=100000.0
    )
    
    print(f"  结果: {'✅ 通过' if result_4.passed else '❌ 拦截'}")
    if result_4.blocked_reason:
        print(f"  拦截原因: {result_4.blocked_reason}")
    
    # 生成审计报告
    print("\n5️⃣ 审计报告...")
    report = risk_agent.get_audit_report()
    print(f"  总检查次数: {report['total_checks']}")
    print(f"  总拦截次数: {report['total_blocks']}")
    print(f"  拦截率: {report['block_rate']:.2%}")
    print(f"  止损修正次数: {report['block_breakdown']['stop_loss_corrections']}")
    print(f"  逆向开仓拦截: {report['block_breakdown']['reverse_position_blocks']}")
    
    print("\n✅ 风控审计官Agent测试通过!")
    return risk_agent


if __name__ == '__main__':
    asyncio.run(test_risk_audit())
