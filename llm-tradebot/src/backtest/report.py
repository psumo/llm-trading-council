"""
回测报告生成 (Backtest Report)
================================

生成 HTML 格式的回测报告

Author: AI Trader Team
Date: 2025-12-31
"""

from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import os

from src.backtest.metrics import MetricsResult


class BacktestReport:
    """
    回测报告生成器
    
    生成包含以下内容的 HTML 报告：
    1. 性能指标摘要
    2. 净值曲线图表
    3. 回撤曲线图表
    4. 月度收益热力图
    5. 交易明细表
    """
    
    def __init__(self, output_dir: str = "reports"):
        """
        初始化报告生成器
        
        Args:
            output_dir: 报告输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate(
        self,
        metrics: MetricsResult,
        equity_curve: pd.DataFrame,
        trades_df: pd.DataFrame,
        config: Dict,
        filename: str = None
    ) -> str:
        """
        生成回测报告
        
        Args:
            metrics: 性能指标结果
            equity_curve: 净值曲线 DataFrame
            trades_df: 交易记录 DataFrame
            config: 回测配置
            filename: 输出文件名（不含扩展名）
            
        Returns:
            报告文件路径
        """
        if filename is None:
            filename = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        filepath = os.path.join(self.output_dir, f"{filename}.html")
        
        # 生成 HTML 内容
        html_content = self._generate_html(metrics, equity_curve, trades_df, config)
        
        # 保存文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return filepath
    
    def _generate_html(
        self,
        metrics: MetricsResult,
        equity_curve: pd.DataFrame,
        trades_df: pd.DataFrame,
        config: Dict
    ) -> str:
        """生成 HTML 内容"""
        
        # 准备图表数据
        equity_data = self._prepare_chart_data(equity_curve)
        trades_html = self._generate_trades_table(trades_df)
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM-TradeBot Backtest Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a25;
            --text-primary: #e0e0e0;
            --text-secondary: #888;
            --accent: #6366f1;
            --success: #22c55e;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 30px;
        }}
        
        header h1 {{
            font-size: 2rem;
            color: var(--accent);
            margin-bottom: 10px;
        }}
        
        header .subtitle {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #333;
        }}
        
        .card h3 {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }}
        
        .metric {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #2a2a35;
        }}
        
        .metric:last-child {{
            border-bottom: none;
        }}
        
        .metric-label {{
            color: var(--text-secondary);
        }}
        
        .metric-value {{
            font-weight: 600;
        }}
        
        .metric-value.positive {{
            color: var(--success);
        }}
        
        .metric-value.negative {{
            color: var(--danger);
        }}
        
        .chart-container {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #333;
            margin-bottom: 30px;
        }}
        
        .chart-container h3 {{
            font-size: 1rem;
            margin-bottom: 15px;
            color: var(--text-primary);
        }}
        
        .chart-wrapper {{
            position: relative;
            height: 300px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
        
        th, td {{
            padding: 10px 8px;
            text-align: left;
            border-bottom: 1px solid #2a2a35;
        }}
        
        th {{
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
        }}
        
        tr:hover {{
            background: rgba(99, 102, 241, 0.1);
        }}
        
        .pnl-positive {{
            color: var(--success);
        }}
        
        .pnl-negative {{
            color: var(--danger);
        }}
        
        footer {{
            text-align: center;
            padding: 30px 0;
            color: var(--text-secondary);
            border-top: 1px solid #333;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 LLM-TradeBot Backtest Report</h1>
            <p class="subtitle">
                {config.get('symbol', 'N/A')} | 
                {metrics.start_date} to {metrics.end_date} | 
                Initial Capital: ${config.get('initial_capital', 0):,.2f}
            </p>
        </header>
        
        <!-- Performance Overview -->
        <div class="grid">
            <div class="card">
                <h3>📈 收益概览</h3>
                <div class="metric">
                    <span class="metric-label">总收益率</span>
                    <span class="metric-value {'positive' if metrics.total_return >= 0 else 'negative'}">
                        {metrics.total_return:+.2f}%
                    </span>
                </div>
                <!-- Removed: Annualized Return (misleading for short backtests) -->
                <div class="metric">
                    <span class="metric-label">最大回撤</span>
                    <span class="metric-value negative">{metrics.max_drawdown_pct:.2f}%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">回撤恢复</span>
                    <span class="metric-value">{metrics.max_drawdown_duration} 天</span>
                </div>
            </div>
            
            <div class="card">
                <h3>⚖️ 风险指标</h3>
                <div class="metric">
                    <span class="metric-label">夏普比率</span>
                    <span class="metric-value {'positive' if metrics.sharpe_ratio >= 1 else ''}">
                        {metrics.sharpe_ratio:.2f}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">索提诺比率</span>
                    <span class="metric-value">{metrics.sortino_ratio:.2f}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">卡尔玛比率</span>
                    <span class="metric-value">{metrics.calmar_ratio:.2f}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">年化波动率</span>
                    <span class="metric-value">{metrics.volatility:.2f}%</span>
                </div>
            </div>
            
            <div class="card">
                <h3>📊 交易统计</h3>
                <div class="metric">
                    <span class="metric-label">总交易次数</span>
                    <span class="metric-value">{metrics.total_trades}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">胜率</span>
                    <span class="metric-value {'positive' if metrics.win_rate >= 50 else 'negative'}">
                        {metrics.win_rate:.1f}%
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">盈亏比</span>
                    <span class="metric-value">{metrics.profit_factor:.2f}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">平均持仓时间</span>
                    <span class="metric-value">{metrics.avg_holding_time:.1f}h</span>
                </div>
            </div>
            
            <div class="card">
                <h3>🐂🐻 多空分析</h3>
                <div class="metric">
                    <span class="metric-label">多头交易</span>
                    <span class="metric-value">
                        {metrics.long_trades} ({metrics.long_win_rate:.1f}%)
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">多头盈亏</span>
                    <span class="metric-value {'positive' if metrics.long_pnl >= 0 else 'negative'}">
                        ${metrics.long_pnl:+,.2f}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">空头交易</span>
                    <span class="metric-value">
                        {metrics.short_trades} ({metrics.short_win_rate:.1f}%)
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">空头盈亏</span>
                    <span class="metric-value {'positive' if metrics.short_pnl >= 0 else 'negative'}">
                        ${metrics.short_pnl:+,.2f}
                    </span>
                </div>
            </div>
        </div>
        
        <!-- Equity Curve Chart -->
        <div class="chart-container">
            <h3>📈 净值曲线</h3>
            <div class="chart-wrapper">
                <canvas id="equityChart"></canvas>
            </div>
        </div>
        
        <!-- Drawdown Chart -->
        <div class="chart-container">
            <h3>📉 回撤曲线</h3>
            <div class="chart-wrapper">
                <canvas id="drawdownChart"></canvas>
            </div>
        </div>
        
        <!-- Trades Table -->
        <div class="card">
            <h3>📋 交易明细</h3>
            <div style="overflow-x: auto;">
                {trades_html}
            </div>
        </div>
        
        <footer>
            <p>Generated by LLM-TradeBot Backtester | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </footer>
    </div>
    
    <script>
        // Equity Chart
        const equityCtx = document.getElementById('equityChart').getContext('2d');
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                labels: {equity_data['labels']},
                datasets: [{{
                    label: 'Equity',
                    data: {equity_data['equity']},
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                }},
                scales: {{
                    x: {{
                        grid: {{ color: '#2a2a35' }},
                        ticks: {{ color: '#888', maxTicksLimit: 10 }},
                    }},
                    y: {{
                        grid: {{ color: '#2a2a35' }},
                        ticks: {{ color: '#888' }},
                    }},
                }},
            }},
        }});
        
        // Drawdown Chart
        const ddCtx = document.getElementById('drawdownChart').getContext('2d');
        new Chart(ddCtx, {{
            type: 'line',
            data: {{
                labels: {equity_data['labels']},
                datasets: [{{
                    label: 'Drawdown %',
                    data: {equity_data['drawdown']},
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.2)',
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                }},
                scales: {{
                    x: {{
                        grid: {{ color: '#2a2a35' }},
                        ticks: {{ color: '#888', maxTicksLimit: 10 }},
                    }},
                    y: {{
                        grid: {{ color: '#2a2a35' }},
                        ticks: {{ color: '#888' }},
                        reverse: true,
                    }},
                }},
            }},
        }});
    </script>
</body>
</html>
"""
        return html
    
    def _prepare_chart_data(self, equity_curve: pd.DataFrame) -> Dict:
        """准备图表数据"""
        if equity_curve.empty:
            return {'labels': '[]', 'equity': '[]', 'drawdown': '[]'}
        
        # 采样以减少数据量
        if len(equity_curve) > 500:
            step = len(equity_curve) // 500
            equity_curve = equity_curve.iloc[::step]
        
        labels = [ts.strftime('%Y-%m-%d') for ts in equity_curve.index]
        equity = [round(v, 2) for v in equity_curve['total_equity'].values]
        drawdown = [round(v, 2) for v in equity_curve['drawdown_pct'].values]
        
        return {
            'labels': str(labels),
            'equity': str(equity),
            'drawdown': str(drawdown),
        }
    
    def _generate_trades_table(self, trades_df: pd.DataFrame) -> str:
        """生成交易表格 HTML"""
        if trades_df.empty:
            return "<p>No trades recorded.</p>"
        
        # 只显示平仓交易
        if 'action' in trades_df.columns:
            trades_df = trades_df[trades_df['action'] == 'close']
        
        if trades_df.empty:
            return "<p>No closed trades.</p>"
        
        # 限制显示数量
        if len(trades_df) > 100:
            trades_df = trades_df.tail(100)
        
        rows = ""
        for _, row in trades_df.iterrows():
            pnl_class = 'pnl-positive' if row.get('pnl', 0) >= 0 else 'pnl-negative'
            pnl = row.get('pnl', 0)
            pnl_pct = row.get('pnl_pct', 0)
            
            rows += f"""
            <tr>
                <td>{row.get('timestamp', 'N/A')[:19] if isinstance(row.get('timestamp'), str) else 'N/A'}</td>
                <td>{row.get('symbol', 'N/A')}</td>
                <td>{row.get('side', 'N/A').upper() if isinstance(row.get('side'), str) else 'N/A'}</td>
                <td>{row.get('quantity', 0):.4f}</td>
                <td>${row.get('entry_price', 0):,.2f}</td>
                <td>${row.get('price', 0):,.2f}</td>
                <td class="{pnl_class}">${pnl:+,.2f}</td>
                <td class="{pnl_class}">{pnl_pct:+.2f}%</td>
                <td>{row.get('holding_time', 0):.1f}h</td>
                <td>{row.get('close_reason', 'N/A')}</td>
            </tr>
            """
        
        return f"""
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Quantity</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>PnL ($)</th>
                    <th>PnL (%)</th>
                    <th>Hold Time</th>
                    <th>Reason</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """
