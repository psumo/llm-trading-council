"""
回测性能指标 (Performance Metrics)
===================================

计算回测的各项性能指标

Author: AI Trader Team
Date: 2025-12-31
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
from datetime import timedelta

from src.backtest.portfolio import Trade, Side


@dataclass
class MetricsResult:
    """性能指标结果"""
    # 收益指标
    total_return: float           # 总收益率 (%)
    annualized_return: float      # 年化收益率 (%)
    final_equity: float           # 最终净值 ($)
    profit_amount: float          # 盈亏金额 ($)
    max_drawdown: float           # 最大回撤 ($)
    max_drawdown_pct: float       # 最大回撤 (%)
    max_drawdown_duration: int    # 最大回撤持续时间 (天)
    
    # 风险指标
    sharpe_ratio: float           # 夏普比率
    sortino_ratio: float          # 索提诺比率
    calmar_ratio: float           # 卡尔玛比率
    volatility: float             # 年化波动率 (%)
    
    # 交易统计
    total_trades: int             # 总交易次数
    winning_trades: int           # 盈利交易次数
    losing_trades: int            # 亏损交易次数
    win_rate: float               # 胜率 (%)
    profit_factor: float          # 盈亏比
    avg_trade_pnl: float          # 平均每笔盈亏 ($)
    avg_win: float                # 平均盈利 ($)
    avg_loss: float               # 平均亏损 ($)
    largest_win: float            # 最大单笔盈利 ($)
    largest_loss: float           # 最大单笔亏损 ($)
    avg_holding_time: float       # 平均持仓时间 (小时)
    
    # 多空统计
    long_trades: int              # 多头交易次数
    short_trades: int             # 空头交易次数
    long_win_rate: float          # 多头胜率 (%)
    short_win_rate: float         # 空头胜率 (%)
    long_pnl: float               # 多头总盈亏 ($)
    short_pnl: float              # 空头总盈亏 ($)
    
    # 时间统计
    start_date: str
    end_date: str
    total_days: int
    trading_days: int
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            # 收益指标
            'total_return': f"{self.total_return:.2f}%",
            # 'annualized_return': f"{self.annualized_return:.2f}%",  # Removed: misleading for short backtests
            'final_equity': f"{self.final_equity:.2f}",
            'profit_amount': f"{self.profit_amount:+.2f}",
            'max_drawdown': f"${self.max_drawdown:.2f}",
            'max_drawdown_pct': f"{self.max_drawdown_pct:.2f}%",
            'max_drawdown_duration': f"{self.max_drawdown_duration} days",
            
            # 风险指标
            'sharpe_ratio': f"{self.sharpe_ratio:.2f}",
            'sortino_ratio': f"{self.sortino_ratio:.2f}",
            'calmar_ratio': f"{self.calmar_ratio:.2f}",
            'volatility': f"{self.volatility:.2f}%",
            
            # 交易统计
            'total_trades': self.total_trades,
            'win_rate': f"{self.win_rate:.1f}%",
            'profit_factor': f"{self.profit_factor:.2f}",
            'avg_trade_pnl': f"${self.avg_trade_pnl:.2f}",
            'avg_win': f"${self.avg_win:.2f}",
            'avg_loss': f"${self.avg_loss:.2f}",
            'largest_win': f"${self.largest_win:.2f}",
            'largest_loss': f"${self.largest_loss:.2f}",
            'avg_holding_time': f"{self.avg_holding_time:.1f}h",
            
            # 多空统计
            'long_trades': self.long_trades,
            'short_trades': self.short_trades,
            'long_win_rate': f"{self.long_win_rate:.1f}%",
            'short_win_rate': f"{self.short_win_rate:.1f}%",
            'long_pnl': f"${self.long_pnl:.2f}",
            'short_pnl': f"${self.short_pnl:.2f}",
            
            # 时间统计
            'period': f"{self.start_date} to {self.end_date}",
            'total_days': self.total_days,
            'trading_days': self.trading_days,
        }


class PerformanceMetrics:
    """
    回测性能指标计算器
    
    计算：
    - 收益类指标（总收益、年化收益、最大回撤）
    - 风险类指标（夏普比率、索提诺比率、波动率）
    - 交易类指标（胜率、盈亏比、平均盈亏）
    """
    
    RISK_FREE_RATE = 0.02  # 无风险利率 (2%)
    TRADING_DAYS_PER_YEAR = 365  # 加密货币 365 天
    
    @classmethod
    def calculate(
        cls,
        equity_curve: pd.DataFrame,
        trades: List[Trade],
        initial_capital: float
    ) -> MetricsResult:
        """
        计算所有性能指标
        
        Args:
            equity_curve: 净值曲线 DataFrame (columns: total_equity, drawdown, drawdown_pct)
            trades: 交易记录列表
            initial_capital: 初始资金
            
        Returns:
            MetricsResult 对象
        """
        # 过滤平仓交易（有 PnL 的交易）
        closed_trades = [t for t in trades if t.action == "close"]
        
        # 计算收益指标
        total_return, annualized_return = cls._calculate_returns(
            equity_curve, initial_capital
        )
        
        # 计算最大回撤
        max_dd, max_dd_pct, max_dd_duration = cls._calculate_max_drawdown(equity_curve)
        
        # 计算风险指标 (使用总收益率而非年化收益率)
        sharpe, sortino, calmar, volatility = cls._calculate_risk_metrics(
            equity_curve, total_return, max_dd_pct  # Changed: use total_return
        )
        
        # 计算交易统计
        trade_stats = cls._calculate_trade_stats(closed_trades)
        
        # 计算多空统计
        long_stats, short_stats = cls._calculate_side_stats(closed_trades)
        
        # 时间统计
        if not equity_curve.empty:
            start_date = equity_curve.index[0].strftime("%Y-%m-%d")
            end_date = equity_curve.index[-1].strftime("%Y-%m-%d")
            total_days = (equity_curve.index[-1] - equity_curve.index[0]).days
        else:
            start_date = end_date = "N/A"
            total_days = 0
        
        trading_days = len(set(t.timestamp.date() for t in closed_trades))
        
        # 计算最终净值和盈亏金额
        final_equity = equity_curve['total_equity'].iloc[-1] if not equity_curve.empty else initial_capital
        profit_amount = final_equity - initial_capital
        
        return MetricsResult(
            # 收益指标
            total_return=total_return,
            annualized_return=annualized_return,
            final_equity=final_equity,
            profit_amount=profit_amount,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_duration=max_dd_duration,
            
            # 风险指标
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            volatility=volatility,
            
            # 交易统计
            total_trades=trade_stats['total'],
            winning_trades=trade_stats['winning'],
            losing_trades=trade_stats['losing'],
            win_rate=trade_stats['win_rate'],
            profit_factor=trade_stats['profit_factor'],
            avg_trade_pnl=trade_stats['avg_pnl'],
            avg_win=trade_stats['avg_win'],
            avg_loss=trade_stats['avg_loss'],
            largest_win=trade_stats['largest_win'],
            largest_loss=trade_stats['largest_loss'],
            avg_holding_time=trade_stats['avg_holding_time'],
            
            # 多空统计
            long_trades=long_stats['count'],
            short_trades=short_stats['count'],
            long_win_rate=long_stats['win_rate'],
            short_win_rate=short_stats['win_rate'],
            long_pnl=long_stats['total_pnl'],
            short_pnl=short_stats['total_pnl'],
            
            # 时间统计
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            trading_days=trading_days,
        )
    
    @classmethod
    def _calculate_returns(
        cls,
        equity_curve: pd.DataFrame,
        initial_capital: float
    ) -> Tuple[float, float]:
        """计算收益率"""
        if equity_curve.empty:
            return 0.0, 0.0
        
        final_equity = equity_curve['total_equity'].iloc[-1]
        total_return = (final_equity - initial_capital) / initial_capital * 100
        
        # 年化收益
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        if days > 0:
            annualized_return = ((1 + total_return / 100) ** (365 / days) - 1) * 100
        else:
            annualized_return = 0.0
        
        return total_return, annualized_return
    
    @classmethod
    def _calculate_max_drawdown(
        cls,
        equity_curve: pd.DataFrame
    ) -> Tuple[float, float, int]:
        """计算最大回撤"""
        if equity_curve.empty:
            return 0.0, 0.0, 0
        
        equity = equity_curve['total_equity']
        
        # 计算滚动最大值
        rolling_max = equity.expanding().max()
        drawdown = rolling_max - equity
        drawdown_pct = drawdown / rolling_max * 100
        
        max_dd = drawdown.max()
        max_dd_pct = drawdown_pct.max()
        
        # 计算最大回撤持续时间
        max_dd_duration = 0
        if max_dd > 0:
            # 找到最大回撤开始和结束的位置
            peak_idx = equity[:drawdown.idxmax()].idxmax()
            recovery_candidates = equity[drawdown.idxmax():]
            recovery_candidates = recovery_candidates[recovery_candidates >= equity[peak_idx]]
            
            if not recovery_candidates.empty:
                recovery_idx = recovery_candidates.index[0]
                max_dd_duration = (recovery_idx - peak_idx).days
            else:
                # 尚未恢复
                max_dd_duration = (equity.index[-1] - peak_idx).days
        
        return max_dd, max_dd_pct, max_dd_duration
    
    @classmethod
    def _calculate_risk_metrics(
        cls,
        equity_curve: pd.DataFrame,
        total_return: float,  # Changed from annualized_return
        max_dd_pct: float
    ) -> Tuple[float, float, float, float]:
        """计算风险指标"""
        if equity_curve.empty or len(equity_curve) < 2:
            return 0.0, 0.0, 0.0, 0.0
        
        # 计算日收益率
        equity = equity_curve['total_equity']
        daily_returns = equity.pct_change().dropna()
        
        if daily_returns.empty:
            return 0.0, 0.0, 0.0, 0.0
        
        # 计算回测期间的波动率 (不年化)
        volatility = daily_returns.std() * 100
        
        # 夏普比率 (使用总收益率,不年化)
        # 对于短期回测,使用总收益率更合理
        risk_free_return = cls.RISK_FREE_RATE * len(daily_returns) / cls.TRADING_DAYS_PER_YEAR * 100
        excess_return = total_return - risk_free_return
        sharpe = excess_return / (volatility * np.sqrt(len(daily_returns))) if volatility > 0 else 0.0
        
        # 索提诺比率（只考虑下行波动）
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0:
            downside_std = negative_returns.std() * 100
            sortino = excess_return / (downside_std * np.sqrt(len(daily_returns))) if downside_std > 0 else 0.0
        else:
            sortino = 0.0
        
        # 卡尔玛比率 (使用总收益率)
        calmar = total_return / max_dd_pct if max_dd_pct > 0 else 0.0
        
        # 年化波动率 (仅用于显示)
        annualized_volatility = daily_returns.std() * np.sqrt(cls.TRADING_DAYS_PER_YEAR) * 100
        
        return sharpe, sortino, calmar, annualized_volatility
    
    @classmethod
    def _calculate_trade_stats(cls, trades: List[Trade]) -> Dict:
        """计算交易统计"""
        if not trades:
            return {
                'total': 0, 'winning': 0, 'losing': 0,
                'win_rate': 0.0, 'profit_factor': 0.0,
                'avg_pnl': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0,
                'largest_win': 0.0, 'largest_loss': 0.0,
                'avg_holding_time': 0.0,
            }
        
        pnls = [t.pnl for t in trades]
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]
        holding_times = [t.holding_time for t in trades if t.holding_time is not None]
        
        total_win = sum(winning) if winning else 0
        total_loss = abs(sum(losing)) if losing else 0
        
        return {
            'total': len(trades),
            'winning': len(winning),
            'losing': len(losing),
            'win_rate': len(winning) / len(trades) * 100 if trades else 0,
            'profit_factor': total_win / total_loss if total_loss > 0 else float('inf'),
            'avg_pnl': sum(pnls) / len(pnls) if pnls else 0,
            'avg_win': sum(winning) / len(winning) if winning else 0,
            'avg_loss': sum(losing) / len(losing) if losing else 0,
            'largest_win': max(pnls) if pnls else 0,
            'largest_loss': min(pnls) if pnls else 0,
            'avg_holding_time': sum(holding_times) / len(holding_times) if holding_times else 0,
        }
    
    @classmethod
    def _calculate_side_stats(cls, trades: List[Trade]) -> Tuple[Dict, Dict]:
        """计算多空分类统计"""
        long_trades = [t for t in trades if t.side == Side.LONG]
        short_trades = [t for t in trades if t.side == Side.SHORT]
        
        def calc_side(trade_list):
            if not trade_list:
                return {'count': 0, 'win_rate': 0.0, 'total_pnl': 0.0}
            
            winning = sum(1 for t in trade_list if t.pnl > 0)
            total_pnl = sum(t.pnl for t in trade_list)
            
            return {
                'count': len(trade_list),
                'win_rate': winning / len(trade_list) * 100,
                'total_pnl': total_pnl,
            }
        
        return calc_side(long_trades), calc_side(short_trades)
    
    @classmethod
    def generate_monthly_returns(cls, equity_curve: pd.DataFrame) -> pd.DataFrame:
        """生成月度收益统计"""
        if equity_curve.empty:
            return pd.DataFrame()
        
        equity = equity_curve['total_equity']
        
        # 重采样到月度
        monthly = equity.resample('M').last()
        monthly_returns = monthly.pct_change() * 100
        
        # 转换为透视表格式（年 x 月）
        monthly_returns = monthly_returns.dropna()
        if monthly_returns.empty:
            return pd.DataFrame()
        
        df = pd.DataFrame({
            'year': monthly_returns.index.year,
            'month': monthly_returns.index.month,
            'return': monthly_returns.values
        })
        
        pivot = df.pivot(index='year', columns='month', values='return')
        pivot.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][:len(pivot.columns)]
        
        return pivot


# 测试函数
def test_metrics():
    """测试性能指标计算"""
    print("\n" + "=" * 60)
    print("🧪 Testing PerformanceMetrics")
    print("=" * 60)
    
    # 创建模拟数据
    from datetime import datetime, timedelta
    
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # 模拟净值曲线
    returns = np.random.normal(0.002, 0.02, 100)
    equity = 10000 * np.cumprod(1 + returns)
    
    equity_curve = pd.DataFrame({
        'total_equity': equity,
        'drawdown': 0,
        'drawdown_pct': 0,
    }, index=dates)
    
    # 模拟交易
    trades = []
    for i in range(10):
        pnl = np.random.uniform(-100, 200)
        trades.append(Trade(
            trade_id=i,
            symbol="BTCUSDT",
            side=Side.LONG if i % 2 == 0 else Side.SHORT,
            action="close",
            quantity=0.01,
            price=50000,
            timestamp=dates[i * 10],
            pnl=pnl,
            pnl_pct=pnl / 500 * 100,
            holding_time=np.random.uniform(1, 48),
        ))
    
    # 计算指标
    metrics = PerformanceMetrics.calculate(equity_curve, trades, 10000)
    
    print("\n📊 Performance Metrics:")
    for k, v in metrics.to_dict().items():
        print(f"   {k}: {v}")
    
    print("\n✅ PerformanceMetrics test complete!")


if __name__ == "__main__":
    test_metrics()
