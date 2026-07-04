"""
特征构建模块 - 为LLM准备输入数据
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
from src.utils.logger import log


class FeatureBuilder:
    """特征构建器 - 将市场数据转换为LLM可理解的上下文"""
    
    def __init__(self):
        pass
    
    def build_market_context(
        self,
        symbol: str,
        multi_timeframe_states: Dict[str, Dict],
        snapshot: Dict,
        position_info: Optional[Dict] = None
    ) -> Dict:
        """
        构建完整的市场上下文
        
        Args:
            symbol: 交易对
            multi_timeframe_states: 多周期市场状态
            snapshot: 市场快照
            position_info: 持仓信息
            
        Returns:
            结构化的市场上下文（包含完整元数据和数据质量验证）
        """
        
        # === 数据质量验证（静默检查）===
        # 验证多周期价格一致性
        price_check = self._validate_multiframe_prices(multi_timeframe_states)
        if not price_check['consistent']:
            log.debug(f"[{symbol}] 多周期价格一致性: {', '.join(price_check['warnings'])}")
        
        # 验证多周期时间对齐
        alignment_check = self._validate_multiframe_alignment(multi_timeframe_states)
        if not alignment_check['aligned']:
            log.debug(f"[{symbol}] 多周期时间对齐: {', '.join(alignment_check['warnings'])}")
        
        # 🆕 验证指标完整性（每个周期）
        indicator_completeness = {}
        for tf, state in multi_timeframe_states.items():
            if 'indicator_completeness' in state:
                indicator_completeness[tf] = state['indicator_completeness']
            else:
                # 如果processor没有提供,标记为未知
                indicator_completeness[tf] = {
                    'is_complete': None,
                    'issues': ['未提供指标完整性检查'],
                    'overall_coverage': None
                }
        
        # 提取当前价格信息
        current_price = snapshot.get('price', {}).get('price', 0)
        
        # 资金费率
        funding_rate = snapshot.get('funding', {}).get('funding_rate', 0)
        
        # 持仓量
        oi_data = snapshot.get('oi', {})
        
        # 订单簿流动性分析
        orderbook = snapshot.get('orderbook', {})
        liquidity_score = self._analyze_liquidity(orderbook)
        
        # 提取账户获取错误（如果有）
        account_fetch_error = snapshot.get('account_error', None)
        
        # 提取快照ID（用于数据一致性追踪）
        snapshot_ids = {}
        for tf, state in multi_timeframe_states.items():
            if 'snapshot_id' in state:
                snapshot_ids[tf] = state['snapshot_id']
        
        # 构建上下文
        context = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            
            # === 数据一致性追踪 ===
            'snapshot_ids': snapshot_ids,  # 各周期的快照ID
            
            # 市场概览
            'market_overview': {
                'current_price': current_price,
                'funding_rate': funding_rate,
                'funding_rate_status': self._classify_funding_rate(funding_rate),
                'open_interest': oi_data.get('open_interest', 0),
                'liquidity': liquidity_score
            },
            
            # 多周期分析
            'multi_timeframe': multi_timeframe_states,
            
            # 持仓上下文
            'position_context': self._build_position_context(
                position_info,
                current_price,
                snapshot.get('account', {}),
                account_fetch_error  # 传递错误信息
            ),
            
            # 风险约束
            'risk_constraints': self._get_risk_constraints(),
            
            # === 🆕 数据质量报告 ===
            'data_quality': {
                'price_consistency': price_check,
                'time_alignment': alignment_check,
                'indicator_completeness': indicator_completeness,
                'overall_score': self._calculate_quality_score(price_check, alignment_check, indicator_completeness)
            }
        }
        
        return context
    
    def _analyze_liquidity(self, orderbook: Dict) -> str:
        """
        分析订单簿流动性
        
        Returns:
            'high', 'medium', 'low'
        """
        if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
            return 'unknown'
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return 'low'
        
        # 计算前5档深度
        bid_depth = sum([q for p, q in bids[:5]])
        ask_depth = sum([q for p, q in asks[:5]])
        
        total_depth = bid_depth + ask_depth
        
        # 简单分类（需要根据实际市场调整阈值）
        if total_depth > 100:
            return 'high'
        elif total_depth > 50:
            return 'medium'
        else:
            return 'low'
    
    def _classify_funding_rate(self, funding_rate: float) -> str:
        """
        分类资金费率
        
        Returns:
            'extremely_positive', 'positive', 'neutral', 'negative', 'extremely_negative'
        """
        if funding_rate > 0.001:
            return 'extremely_positive'
        elif funding_rate > 0.0003:
            return 'positive'
        elif funding_rate < -0.001:
            return 'extremely_negative'
        elif funding_rate < -0.0003:
            return 'negative'
        else:
            return 'neutral'
    
    def _build_position_context(
        self,
        position: Optional[Dict],
        current_price: float,
        account: Optional[Dict],
        account_fetch_error: Optional[str] = None
    ) -> Dict:
        """
        构建持仓上下文
        
        重要：不要将 None/缺失 转换为 0，要明确标注
        """
        
        # 如果没有账户信息，明确标注为 None
        if not account or account_fetch_error:
            return {
                'has_position': False,
                'side': 'NONE',
                'size': None,  # 明确标注为 None，不是 0
                'entry_price': None,
                'current_pnl_pct': None,
                'unrealized_pnl': None,
                'account_balance': None,  # 重要：None 不是 0
                'total_balance': None,
                'margin_usage_pct': None,
                'account_fetch_error': account_fetch_error or 'No account data available',
                'warning': '⚠️ Account info missing, trading is not recommended'
            }
        
        if not position or position.get('position_amt', 0) == 0:
            return {
                'has_position': False,
                'side': 'NONE',
                'size': 0,
                'entry_price': 0,
                'current_pnl_pct': 0,
                'unrealized_pnl': 0,
                'account_balance': account.get('available_balance', 0),
                'total_balance': account.get('total_wallet_balance', 0),
                'margin_usage_pct': 0,
                'account_fetch_error': None
            }
        
        position_amt = position.get('position_amt', 0)
        entry_price = position.get('entry_price', 0)
        unrealized_pnl = position.get('unrealized_profit', 0)
        
        # 计算盈亏百分比
        if entry_price > 0:
            if position_amt > 0:  # LONG
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:  # SHORT
                pnl_pct = (entry_price - current_price) / entry_price * 100
        else:
            pnl_pct = 0
        
        # 计算保证金使用率
        total_balance = account.get('total_wallet_balance', 0)
        margin_balance = account.get('total_margin_balance', 0)
        
        margin_usage_pct = 0
        if total_balance > 0:
            margin_usage_pct = (margin_balance / total_balance) * 100
        
        return {
            'has_position': True,
            'side': 'LONG' if position_amt > 0 else 'SHORT',
            'size': abs(position_amt),
            'entry_price': entry_price,
            'current_price': current_price,
            'current_pnl_pct': round(pnl_pct, 2),
            'unrealized_pnl': unrealized_pnl,
            'account_balance': account.get('available_balance', 0),
            'total_balance': total_balance,
            'margin_usage_pct': round(margin_usage_pct, 2),
            'leverage': position.get('leverage', 1),
            'account_fetch_error': None
        }
    
    def _get_risk_constraints(self) -> Dict:
        """获取风险约束配置"""
        from src.config import config
        
        return {
            'max_risk_per_trade_pct': config.risk.get('max_risk_per_trade_pct', 1.5),
            'max_total_position_pct': config.risk.get('max_total_position_pct', 30.0),
            'max_leverage': config.risk.get('max_leverage', 5),
            'max_consecutive_losses': config.risk.get('max_consecutive_losses', 3)
        }
    
    def format_for_llm(self, context: Dict) -> str:
        """
        将上下文格式化为LLM友好的文本
        
        这是提供给DeepSeek的最终输入
        """
        
        market = context['market_overview']
        position = context['position_context']
        mtf = context['multi_timeframe']
        constraints = context['risk_constraints']
        
        # 构建文本描述
        text = f"""
## 市场快照 ({context['timestamp']})

**交易对**: {context['symbol']}
**当前价格**: ${market['current_price']:,.2f}

### 市场状态总览
- **资金费率**: {market['funding_rate']:.4%} ({market['funding_rate_status']})
  → 资金费率反映多空力量对比，正值表示多头支付空头，负值相反
- **持仓量(OI)**: {market['open_interest']:,.0f}
  → 持仓量增加通常表示新资金入场，减少表示资金流出
- **流动性深度**: {market['liquidity']}
  → 反映订单簿深度，影响大单的滑点

### 多周期分析
→ 建议：综合多个时间周期判断，大周期确定趋势方向，小周期寻找入场时机
"""
        
        # 添加多周期状态（按时间周期排序，从小到大）
        timeframe_order = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
        sorted_tfs = sorted(mtf.keys(), key=lambda x: timeframe_order.index(x) if x in timeframe_order else 999)
        
        for tf in sorted_tfs:
            state = mtf[tf]
            text += f"\n**{tf}**:\n"
            text += f"  - 趋势: {state.get('trend', 'N/A')}\n"
            text += f"  - 波动率: {state.get('volatility', 'N/A')} (ATR: {state.get('atr_pct', 'N/A')}%)\n"
            text += f"  - 动量: {state.get('momentum', 'N/A')}\n"
            text += f"  - RSI: {state.get('rsi', 'N/A')}\n"
            text += f"  - MACD信号: {state.get('macd_signal', 'N/A')}\n"
            text += f"  - 成交量比率: {state.get('volume_ratio', 'N/A')}\n"
            text += f"  - 成交量变化: {state.get('volume_change_pct', 'N/A')}%\n"
            text += f"  - 当前价格: ${state.get('price', 'N/A')}\n"
            
            # 关键价位
            levels = state.get('key_levels', {})
            if levels.get('support'):
                text += f"  - 支撑位: {levels['support']}\n"
            if levels.get('resistance'):
                text += f"  - 阻力位: {levels['resistance']}\n"
        
        # 持仓信息
        text += "\n### 当前持仓\n"
        if position.get('account_fetch_error'):
            # 账户信息获取失败
            text += f"⚠️ **警告**: {position['warning']}\n"
            text += f"- 错误原因: {position['account_fetch_error']}\n"
            text += "- Position Status: Unable to fetch\n"
            text += "- Account Balance: Unable to fetch\n"
            text += "\n**Important**: Account info unavailable. Recommendations:\n"
            text += "  1. Do not open any new positions\n"
            text += "  2. Check if API key is correctly configured\n"
            text += "  3. Verify API permissions include account query\n"
        elif position['has_position']:
            text += f"- 方向: {position['side']}\n"
            text += f"- 数量: {position['size']}\n"
            text += f"- 入场价: ${position['entry_price']:,.2f}\n"
            text += f"- 当前盈亏: {position['current_pnl_pct']:.2f}%\n"
            text += f"- 未实现盈亏: ${position['unrealized_pnl']:,.2f}\n"
            text += f"- 杠杆: {position['leverage']}x\n"
            text += f"- 保证金使用率: {position['margin_usage_pct']:.1f}%\n"
        else:
            text += "- 无持仓\n"
        
        text += f"\n### 账户信息\n"
        if position.get('account_fetch_error'):
            text += "- Available Balance: **Unable to fetch**\n"
            text += "- Total Balance: **Unable to fetch**\n"
        else:
            balance = position.get('account_balance')
            total = position.get('total_balance', 0)
            text += f"- 可用余额: ${balance:,.2f}\n" if balance is not None else "- 可用余额: **未知**\n"
            text += f"- 总余额: ${total:,.2f}\n"
        
        # 风险约束
        text += f"\n### 风险约束\n"
        text += f"- 单笔最大风险: {constraints['max_risk_per_trade_pct']}%\n"
        text += f"- 最大总仓位: {constraints['max_total_position_pct']}%\n"
        text += f"- 最大杠杆: {constraints['max_leverage']}x\n"
        text += f"- 最大连续亏损: {constraints['max_consecutive_losses']}次\n"
        
        # 添加决策指引
        text += f"\n### 决策要求\n"
        text += "请基于以上信息进行综合分析：\n"
        text += "1. **多周期趋势一致性**: 检查不同周期的趋势是否一致\n"
        text += "2. **动量与波动率**: 评估市场动能和波动性\n"
        text += "3. **技术指标共振**: RSI、MACD等指标是否发出一致信号\n"
        text += "4. **资金费率与OI**: 分析市场情绪和资金流向\n"
        text += "5. **支撑阻力位**: 考虑关键价位对价格的影响\n"
        text += "6. **风险收益比**: 确保潜在收益至少是风险的2倍以上\n"
        text += "7. **持仓管理**: 如有持仓，考虑是否需要调整或止盈止损\n"
        
        return text
    
    def _validate_multiframe_prices(self, multi_timeframe_states: Dict[str, Dict]) -> Dict:
        """
        验证多周期价格一致性
        
        检查不同时间周期的收盘价是否一致
        """
        all_prices = []
        warnings = []
        
        for tf, state in multi_timeframe_states.items():
            if 'close' in state:
                all_prices.append(state['close'])
            else:
                warnings.append(f"{tf} 缺失收盘价")
        
        # 检查一致性
        if len(set(all_prices)) > 1:
            warnings.append("不同周期的收盘价不一致")
        
        return {
            'consistent': len(warnings) == 0,
            'warnings': warnings
        }
    
    def _validate_multiframe_alignment(self, multi_timeframe_states: Dict[str, Dict]) -> Dict:
        """
        验证多周期时间对齐
        
        检查不同时间周期的时间戳是否对齐
        """
        all_times = []
        warnings = []
        
        for tf, state in multi_timeframe_states.items():
            if 'timestamp' in state:
                all_times.append(state['timestamp'])
            else:
                warnings.append(f"{tf} 缺失时间戳")
        
        # 检查对齐情况
        if len(set(all_times)) > 1:
            warnings.append("不同周期的时间戳不一致")
        
        return {
            'aligned': len(warnings) == 0,
            'warnings': warnings
        }
    
    def _calculate_quality_score(self, price_check: Dict, alignment_check: Dict, indicator_completeness: Dict) -> float:
        """
        计算数据质量分数
        
        综合考虑:
        1. 价格一致性 (权重: 30%)
        2. 时间对齐 (权重: 20%)
        3. 指标完整性 (权重: 50%)
        
        Returns:
            质量分数 (0-100)
        """
        score = 100.0
        
        # 1. 价格一致性检查 (-30分)
        if not price_check.get('consistent', True):
            score -= 30
        elif len(price_check.get('warnings', [])) > 0:
            score -= 15  # 有警告但不严重
        
        # 2. 时间对齐检查 (-20分)
        if not alignment_check.get('aligned', True):
            score -= 20
        
        # 3. 指标完整性检查 (-50分)
        # 计算所有周期的平均完整性
        completeness_scores = []
        for tf, comp in indicator_completeness.items():
            if comp.get('is_complete') is True:
                completeness_scores.append(100.0)
            elif comp.get('overall_coverage') is not None:
                # 按覆盖率打分
                completeness_scores.append(comp['overall_coverage'] * 100)
            else:
                completeness_scores.append(0.0)
        
        if completeness_scores:
            avg_completeness = sum(completeness_scores) / len(completeness_scores)
            # 完整性权重50%
            score -= (100 - avg_completeness) * 0.5
        else:
            score -= 50  # 无法评估完整性，扣满分
        
        return max(score, 0.0)  # 分数不低于 0
