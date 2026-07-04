"""
Backtest Data Storage Manager

Provides persistent storage for backtest results using SQLite database.
Supports CRUD operations, batch import/export, and data migration.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import pandas as pd


class BacktestStorage:
    """Manages persistent storage of backtest results"""
    
    def __init__(self, db_path: str = None):
        """
        Initialize storage manager
        
        Args:
            db_path: Path to SQLite database file. Defaults to data/backtest_analytics.db
        """
        if db_path is None:
            base_dir = Path(__file__).parent.parent.parent
            data_dir = base_dir / 'data' / 'backtest'  # New: use data/backtest/ directory
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / 'backtest_analytics.db')
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Backtest runs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                run_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                symbols TEXT,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                initial_capital REAL NOT NULL,
                step INTEGER NOT NULL,
                stop_loss_pct REAL,
                take_profit_pct REAL,
                leverage INTEGER,
                margin_mode TEXT,
                contract_type TEXT,
                fee_tier TEXT,
                include_funding BOOLEAN,
                duration_seconds REAL,
                status TEXT DEFAULT 'completed'
            )
        ''')
        
        # Metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                total_return TEXT,
                annualized_return TEXT,
                max_drawdown_pct TEXT,
                sharpe_ratio TEXT,
                sortino_ratio TEXT,
                win_rate TEXT,
                total_trades INTEGER,
                profit_factor TEXT,
                long_trades INTEGER,
                short_trades INTEGER,
                long_win_rate TEXT,
                short_win_rate TEXT,
                avg_holding_time TEXT,
                volatility TEXT,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
            )
        ''')
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                trade_id INTEGER,
                symbol TEXT,
                side TEXT,
                action TEXT,
                quantity REAL,
                price REAL,
                timestamp TIMESTAMP,
                pnl REAL,
                pnl_pct REAL,
                entry_price REAL,
                holding_time REAL,
                close_reason TEXT,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
            )
        ''')
        
        # Equity curve table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TIMESTAMP,
                total_equity REAL,
                cash REAL,
                position_value REAL,
                drawdown_pct REAL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
            )
        ''')
        
        # Optimization sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS optimization_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                optimization_target TEXT,
                parameter_space TEXT,
                best_run_id TEXT,
                status TEXT DEFAULT 'running'
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_run_id ON backtest_runs(run_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON backtest_runs(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_run_time ON backtest_runs(run_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_run_id ON backtest_trades(run_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_equity_run_id ON backtest_equity(run_id)')
        
        conn.commit()
        conn.close()
    
    def save_backtest(self, run_id: str, config: Dict, metrics: Dict, 
                     trades: List[Dict], equity_curve: List[Dict]) -> bool:
        """
        Save complete backtest results
        
        Args:
            run_id: Unique identifier for this backtest run
            config: Backtest configuration
            metrics: Performance metrics
            trades: List of trade records
            equity_curve: Equity curve data points
            
        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Save run configuration
            cursor.execute('''
                INSERT INTO backtest_runs (
                    run_id, symbol, symbols, start_date, end_date,
                    initial_capital, step, stop_loss_pct, take_profit_pct,
                    leverage, margin_mode, contract_type, fee_tier,
                    include_funding, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                config.get('symbol'),
                json.dumps(config.get('symbols', [])),
                config.get('start_date'),
                config.get('end_date'),
                config.get('initial_capital'),
                config.get('step'),
                config.get('stop_loss_pct'),
                config.get('take_profit_pct'),
                config.get('leverage'),
                config.get('margin_mode'),
                config.get('contract_type'),
                config.get('fee_tier'),
                config.get('include_funding'),
                config.get('duration_seconds')
            ))
            
            # Save metrics
            cursor.execute('''
                INSERT INTO backtest_metrics (
                    run_id, total_return, annualized_return, max_drawdown_pct,
                    sharpe_ratio, sortino_ratio, win_rate, total_trades,
                    profit_factor, long_trades, short_trades, long_win_rate,
                    short_win_rate, avg_holding_time, volatility
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                metrics.get('total_return'),
                metrics.get('annualized_return'),
                metrics.get('max_drawdown_pct'),
                metrics.get('sharpe_ratio'),
                metrics.get('sortino_ratio'),
                metrics.get('win_rate'),
                metrics.get('total_trades'),
                metrics.get('profit_factor'),
                metrics.get('long_trades'),
                metrics.get('short_trades'),
                metrics.get('long_win_rate'),
                metrics.get('short_win_rate'),
                metrics.get('avg_holding_time'),
                metrics.get('volatility')
            ))
            
            # Save trades
            for trade in trades:
                cursor.execute('''
                    INSERT INTO backtest_trades (
                        run_id, trade_id, symbol, side, action, quantity,
                        price, timestamp, pnl, pnl_pct, entry_price,
                        holding_time, close_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    run_id,
                    trade.get('trade_id'),
                    trade.get('symbol'),
                    trade.get('side'),
                    trade.get('action'),
                    trade.get('quantity'),
                    trade.get('price'),
                    trade.get('timestamp'),
                    trade.get('pnl'),
                    trade.get('pnl_pct'),
                    trade.get('entry_price'),
                    trade.get('holding_time'),
                    trade.get('close_reason')
                ))
            
            # Save equity curve
            for point in equity_curve:
                cursor.execute('''
                    INSERT INTO backtest_equity (
                        run_id, timestamp, total_equity, cash,
                        position_value, drawdown_pct
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    run_id,
                    point.get('timestamp'),
                    point.get('total_equity'),
                    point.get('cash'),
                    point.get('position_value'),
                    point.get('drawdown_pct')
                ))
            
            conn.commit()
            
            # Get the auto-increment ID
            backtest_id = cursor.lastrowid
            
            conn.close()
            return backtest_id
            
        except Exception as e:
            print(f"Error saving backtest: {e}")
            return None
    
    def get_backtest(self, run_id: str) -> Optional[Dict]:
        """
        Retrieve complete backtest results
        
        Args:
            run_id: Backtest run identifier
            
        Returns:
            Dictionary with config, metrics, trades, equity_curve
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get run config
            cursor.execute('SELECT * FROM backtest_runs WHERE run_id = ?', (run_id,))
            run = cursor.fetchone()
            if not run:
                return None
            
            # Get metrics
            cursor.execute('SELECT * FROM backtest_metrics WHERE run_id = ?', (run_id,))
            metrics = cursor.fetchone()
            
            # Get trades
            cursor.execute('SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY timestamp', (run_id,))
            trades = cursor.fetchall()
            
            # Get equity curve
            cursor.execute('SELECT * FROM backtest_equity WHERE run_id = ? ORDER BY timestamp', (run_id,))
            equity = cursor.fetchall()
            
            conn.close()
            
            return {
                'config': dict(run),
                'metrics': dict(metrics) if metrics else {},
                'trades': [dict(t) for t in trades],
                'equity_curve': [dict(e) for e in equity]
            }
            
        except Exception as e:
            print(f"Error retrieving backtest: {e}")
            return None
    
    def list_backtests(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """
        List backtest runs with optional filtering
        
        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of results
            
        Returns:
            List of backtest summaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = '''
                SELECT r.*, m.total_return, m.sharpe_ratio, m.max_drawdown_pct, m.total_trades
                FROM backtest_runs r
                LEFT JOIN backtest_metrics m ON r.run_id = m.run_id
            '''
            
            if symbol:
                query += ' WHERE r.symbol = ?'
                cursor.execute(query + ' ORDER BY r.run_time DESC LIMIT ?', (symbol, limit))
            else:
                cursor.execute(query + ' ORDER BY r.run_time DESC LIMIT ?', (limit,))
            
            results = cursor.fetchall()
            conn.close()
            
            return [dict(r) for r in results]
            
        except Exception as e:
            print(f"Error listing backtests: {e}")
            return []
    
    def delete_backtest(self, run_id: str) -> bool:
        """Delete a backtest and all related data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM backtest_equity WHERE run_id = ?', (run_id,))
            cursor.execute('DELETE FROM backtest_trades WHERE run_id = ?', (run_id,))
            cursor.execute('DELETE FROM backtest_metrics WHERE run_id = ?', (run_id,))
            cursor.execute('DELETE FROM backtest_runs WHERE run_id = ?', (run_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error deleting backtest: {e}")
            return False
    
    def export_to_csv(self, run_id: str, output_dir: str) -> bool:
        """Export backtest data to CSV files"""
        try:
            data = self.get_backtest(run_id)
            if not data:
                return False
            
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Export trades
            if data['trades']:
                trades_df = pd.DataFrame(data['trades'])
                trades_df.to_csv(output_path / f'{run_id}_trades.csv', index=False)
            
            # Export equity curve
            if data['equity_curve']:
                equity_df = pd.DataFrame(data['equity_curve'])
                equity_df.to_csv(output_path / f'{run_id}_equity.csv', index=False)
            
            # Export config and metrics as JSON
            summary = {
                'config': data['config'],
                'metrics': data['metrics']
            }
            with open(output_path / f'{run_id}_summary.json', 'w') as f:
                json.dump(summary, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error exporting backtest: {e}")
            return False
