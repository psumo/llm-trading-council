"""
Backtest Analytics Tools

Provides analysis functions for comparing backtests, identifying trends,
and generating optimization recommendations.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from .storage import BacktestStorage


class BacktestAnalytics:
    """Analytics tools for backtest results"""
    
    def __init__(self, storage: BacktestStorage = None):
        """
        Initialize analytics engine
        
        Args:
            storage: BacktestStorage instance. Creates new one if not provided.
        """
        self.storage = storage or BacktestStorage()
    
    def compare_runs(self, run_ids: List[str]) -> pd.DataFrame:
        """
        Compare multiple backtest runs
        
        Args:
            run_ids: List of run IDs to compare
            
        Returns:
            DataFrame with comparison metrics
        """
        results = []
        
        for run_id in run_ids:
            data = self.storage.get_backtest(run_id)
            if not data:
                continue
            
            config = data['config']
            metrics = data['metrics']
            
            results.append({
                'run_id': run_id,
                'run_time': config.get('run_time'),
                'symbol': config.get('symbol'),
                'period': f"{config.get('start_date')} to {config.get('end_date')}",
                'capital': config.get('initial_capital'),
                'leverage': config.get('leverage'),
                'stop_loss': config.get('stop_loss_pct'),
                'take_profit': config.get('take_profit_pct'),
                'total_return': metrics.get('total_return'),
                'sharpe_ratio': metrics.get('sharpe_ratio'),
                'max_drawdown': metrics.get('max_drawdown_pct'),
                'win_rate': metrics.get('win_rate'),
                'total_trades': metrics.get('total_trades'),
                'profit_factor': metrics.get('profit_factor')
            })
        
        return pd.DataFrame(results)
    
    def get_performance_trends(self, symbol: str, days: int = 30) -> Dict:
        """
        Analyze performance trends over time
        
        Args:
            symbol: Trading symbol
            days: Number of days to analyze
            
        Returns:
            Dictionary with trend analysis
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Get recent backtests
        all_runs = self.storage.list_backtests(symbol=symbol, limit=1000)
        recent_runs = [
            r for r in all_runs 
            if datetime.fromisoformat(r['run_time']) > cutoff_date
        ]
        
        if not recent_runs:
            return {'error': 'No recent backtests found'}
        
        df = pd.DataFrame(recent_runs)
        
        # Convert metrics to numeric
        numeric_cols = ['total_return', 'sharpe_ratio', 'max_drawdown_pct']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].str.rstrip('%'), errors='coerce')
        
        return {
            'symbol': symbol,
            'period_days': days,
            'total_backtests': len(recent_runs),
            'avg_return': df['total_return'].mean() if 'total_return' in df else None,
            'avg_sharpe': df['sharpe_ratio'].mean() if 'sharpe_ratio' in df else None,
            'avg_drawdown': df['max_drawdown_pct'].mean() if 'max_drawdown_pct' in df else None,
            'best_run': {
                'run_id': df.loc[df['total_return'].idxmax(), 'run_id'] if 'total_return' in df else None,
                'return': df['total_return'].max() if 'total_return' in df else None
            },
            'worst_run': {
                'run_id': df.loc[df['total_return'].idxmin(), 'run_id'] if 'total_return' in df else None,
                'return': df['total_return'].min() if 'total_return' in df else None
            }
        }
    
    def suggest_optimal_parameters(self, symbol: str, target: str = 'sharpe') -> Dict:
        """
        Suggest optimal parameters based on historical backtests
        
        Args:
            symbol: Trading symbol
            target: Optimization target ('sharpe', 'return', 'drawdown')
            
        Returns:
            Dictionary with parameter recommendations
        """
        runs = self.storage.list_backtests(symbol=symbol, limit=500)
        if not runs:
            return {'error': 'No backtest data available'}
        
        df = pd.DataFrame(runs)
        
        # Convert metrics to numeric
        if target == 'sharpe':
            df['target'] = pd.to_numeric(df['sharpe_ratio'], errors='coerce')
        elif target == 'return':
            df['target'] = pd.to_numeric(df['total_return'].str.rstrip('%'), errors='coerce')
        elif target == 'drawdown':
            df['target'] = -pd.to_numeric(df['max_drawdown_pct'].str.rstrip('%'), errors='coerce')
        
        # Remove NaN values
        df = df.dropna(subset=['target'])
        
        if df.empty:
            return {'error': 'Insufficient data for optimization'}
        
        # Find best performing run
        best_idx = df['target'].idxmax()
        best_run = df.loc[best_idx]
        
        # Calculate parameter statistics
        param_stats = {}
        for param in ['leverage', 'stop_loss_pct', 'take_profit_pct', 'step']:
            if param in df.columns:
                param_stats[param] = {
                    'best_value': best_run.get(param),
                    'mean': df[param].mean(),
                    'median': df[param].median(),
                    'std': df[param].std()
                }
        
        return {
            'symbol': symbol,
            'target': target,
            'best_run_id': best_run['run_id'],
            'best_score': float(best_run['target']),
            'recommended_params': {
                'leverage': int(best_run.get('leverage', 10)),
                'stop_loss_pct': float(best_run.get('stop_loss_pct', 1.0)),
                'take_profit_pct': float(best_run.get('take_profit_pct', 2.0)),
                'step': int(best_run.get('step', 3))
            },
            'parameter_statistics': param_stats,
            'sample_size': len(df)
        }
    
    def analyze_parameter_impact(self, symbol: str, parameter: str) -> pd.DataFrame:
        """
        Analyze impact of a specific parameter on performance
        
        Args:
            symbol: Trading symbol
            parameter: Parameter name (e.g., 'leverage', 'stop_loss_pct')
            
        Returns:
            DataFrame with parameter values and corresponding metrics
        """
        runs = self.storage.list_backtests(symbol=symbol, limit=500)
        if not runs:
            return pd.DataFrame()
        
        df = pd.DataFrame(runs)
        
        # Convert metrics to numeric
        for col in ['total_return', 'sharpe_ratio', 'max_drawdown_pct']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].str.rstrip('%'), errors='coerce')
        
        # Group by parameter value
        if parameter in df.columns:
            grouped = df.groupby(parameter).agg({
                'total_return': ['mean', 'std', 'count'],
                'sharpe_ratio': ['mean', 'std'],
                'max_drawdown_pct': ['mean', 'std']
            }).reset_index()
            
            return grouped
        
        return pd.DataFrame()
    
    def get_win_rate_analysis(self, run_id: str) -> Dict:
        """
        Detailed win rate analysis for a specific backtest
        
        Args:
            run_id: Backtest run identifier
            
        Returns:
            Dictionary with win rate breakdown
        """
        data = self.storage.get_backtest(run_id)
        if not data or not data['trades']:
            return {'error': 'No trade data available'}
        
        trades_df = pd.DataFrame(data['trades'])
        
        # Calculate win/loss
        trades_df['is_win'] = trades_df['pnl'] > 0
        
        analysis = {
            'total_trades': len(trades_df),
            'winning_trades': trades_df['is_win'].sum(),
            'losing_trades': (~trades_df['is_win']).sum(),
            'win_rate': (trades_df['is_win'].sum() / len(trades_df) * 100) if len(trades_df) > 0 else 0,
            'avg_win': trades_df[trades_df['is_win']]['pnl'].mean() if trades_df['is_win'].any() else 0,
            'avg_loss': trades_df[~trades_df['is_win']]['pnl'].mean() if (~trades_df['is_win']).any() else 0,
            'largest_win': trades_df['pnl'].max(),
            'largest_loss': trades_df['pnl'].min(),
            'avg_holding_time_hours': trades_df['holding_time'].mean() if 'holding_time' in trades_df else None
        }
        
        # Side-specific analysis
        if 'side' in trades_df.columns:
            for side in ['long', 'short']:
                side_trades = trades_df[trades_df['side'] == side]
                if len(side_trades) > 0:
                    analysis[f'{side}_trades'] = len(side_trades)
                    analysis[f'{side}_win_rate'] = (side_trades['is_win'].sum() / len(side_trades) * 100)
        
        return analysis
    
    def calculate_risk_metrics(self, run_id: str) -> Dict:
        """
        Calculate advanced risk metrics
        
        Args:
            run_id: Backtest run identifier
            
        Returns:
            Dictionary with risk metrics
        """
        data = self.storage.get_backtest(run_id)
        if not data or not data['equity_curve']:
            return {'error': 'No equity curve data available'}
        
        equity_df = pd.DataFrame(data['equity_curve'])
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
        equity_df = equity_df.sort_values('timestamp')
        
        # Calculate returns
        equity_df['returns'] = equity_df['total_equity'].pct_change()
        
        # Risk metrics
        returns = equity_df['returns'].dropna()
        
        metrics = {
            'volatility': returns.std() * np.sqrt(252),  # Annualized
            'downside_deviation': returns[returns < 0].std() * np.sqrt(252),
            'max_consecutive_losses': self._max_consecutive_losses(equity_df),
            'calmar_ratio': self._calculate_calmar_ratio(equity_df),
            'recovery_time_days': self._calculate_recovery_time(equity_df)
        }
        
        return metrics
    
    def _max_consecutive_losses(self, equity_df: pd.DataFrame) -> int:
        """Calculate maximum consecutive losing days"""
        equity_df['is_loss'] = equity_df['returns'] < 0
        consecutive = 0
        max_consecutive = 0
        
        for is_loss in equity_df['is_loss']:
            if is_loss:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        
        return max_consecutive
    
    def _calculate_calmar_ratio(self, equity_df: pd.DataFrame) -> float:
        """Calculate Calmar ratio (return / max drawdown)"""
        total_return = (equity_df['total_equity'].iloc[-1] / equity_df['total_equity'].iloc[0] - 1)
        max_dd = equity_df['drawdown_pct'].min() / 100
        
        if max_dd == 0:
            return 0
        
        return total_return / abs(max_dd)
    
    def _calculate_recovery_time(self, equity_df: pd.DataFrame) -> Optional[int]:
        """Calculate time to recover from maximum drawdown (in days)"""
        # Find max drawdown point
        max_dd_idx = equity_df['drawdown_pct'].idxmin()
        
        # Find recovery point (when equity exceeds previous peak)
        peak_equity = equity_df.loc[:max_dd_idx, 'total_equity'].max()
        recovery_df = equity_df.loc[max_dd_idx:]
        recovery_point = recovery_df[recovery_df['total_equity'] >= peak_equity]
        
        if recovery_point.empty:
            return None  # Not recovered yet
        
        recovery_idx = recovery_point.index[0]
        time_diff = equity_df.loc[recovery_idx, 'timestamp'] - equity_df.loc[max_dd_idx, 'timestamp']
        
        return time_diff.days
