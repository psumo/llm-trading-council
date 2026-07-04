# Backtest Analytics System

## 概述

完整的回测数据分析系统，支持：

- ✅ SQLite 数据库持久化存储
- ✅ 批量对比分析
- ✅ 参数优化建议
- ✅ 性能趋势分析
- ✅ 风险指标计算
- ✅ 数据导出（CSV/JSON）

## 数据库结构

### 表设计

- `backtest_runs` - 回测运行配置
- `backtest_metrics` - 性能指标
- `backtest_trades` - 交易记录
- `backtest_equity` - 净值曲线
- `optimization_sessions` - 优化会话

### 数据库位置

```
data/backtest_analytics.db
```

## API 端点

### 1. 列出回测

```http
GET /api/backtest/list?symbol=BTCUSDT&limit=100
```

### 2. 对比回测

```http
POST /api/backtest/compare
{
  "run_ids": ["bt_abc123", "bt_def456"]
}
```

### 3. 性能趋势

```http
GET /api/backtest/trends?symbol=BTCUSDT&days=30
```

### 4. 参数优化建议

```http
GET /api/backtest/optimize/suggest?symbol=BTCUSDT&target=sharpe
```

- `target`: `sharpe` | `return` | `drawdown`

### 5. 详细分析

```http
GET /api/backtest/analyze/{run_id}
```

返回：

- 胜率分析
- 风险指标
- 持仓时间统计

### 6. 导出数据

```http
GET /api/backtest/export/{run_id}?format=csv
```

- `format`: `csv` | `json`

### 7. 删除回测

```http
DELETE /api/backtest/{run_id}
```

## Python API 使用

### 存储管理

```python
from src.backtest.storage import BacktestStorage

storage = BacktestStorage()

# 保存回测
storage.save_backtest(
    run_id="bt_001",
    config={...},
    metrics={...},
    trades=[...],
    equity_curve=[...]
)

# 获取回测
data = storage.get_backtest("bt_001")

# 列出回测
backtests = storage.list_backtests(symbol="BTCUSDT", limit=100)

# 导出
storage.export_to_csv("bt_001", "/path/to/output")

# 删除
storage.delete_backtest("bt_001")
```

### 分析工具

```python
from src.backtest.analytics import BacktestAnalytics

analytics = BacktestAnalytics()

# 对比分析
comparison = analytics.compare_runs(["bt_001", "bt_002"])

# 性能趋势
trends = analytics.get_performance_trends("BTCUSDT", days=30)

# 参数建议
suggestions = analytics.suggest_optimal_parameters("BTCUSDT", target="sharpe")

# 参数影响分析
impact = analytics.analyze_parameter_impact("BTCUSDT", "leverage")

# 胜率分析
win_analysis = analytics.get_win_rate_analysis("bt_001")

# 风险指标
risk_metrics = analytics.calculate_risk_metrics("bt_001")
```

## 测试

运行测试脚本验证功能：

```bash
python src/backtest/test_analytics.py
```

## 数据迁移

### 从 localStorage 迁移

如果需要将浏览器 localStorage 中的历史数据迁移到数据库：

```python
from src.backtest.storage import BacktestStorage
import json

storage = BacktestStorage()

# 从浏览器导出的 localStorage 数据
with open('backtest_history.json', 'r') as f:
    history = json.load(f)

for item in history:
    storage.save_backtest(
        run_id=f"bt_{item['id']}",
        config={
            'symbol': item['symbol'],
            'symbols': item.get('symbols', [item['symbol']]),
            'start_date': item['startDate'],
            'end_date': item['endDate'],
            'initial_capital': item['initialCapital'],
            'step': item['step'],
            'stop_loss_pct': item['stopLoss'],
            'take_profit_pct': item['takeProfit'],
            'leverage': item.get('leverage', 10),
            'margin_mode': item.get('marginMode', 'cross'),
            'duration_seconds': item.get('duration', 0)
        },
        metrics={
            'total_return': item['totalReturn'],
            'win_rate': item['winRate'],
            'total_trades': item['trades'],
            'max_drawdown_pct': item.get('maxDrawdown'),
            'sharpe_ratio': item.get('sharpeRatio'),
            'profit_factor': item.get('profitFactor')
        },
        trades=item.get('tradesList', []),
        equity_curve=item.get('equityCurve', [])
    )
```

## 性能优化

### 数据库索引

已创建以下索引以提高查询性能：

- `idx_run_id` - 运行 ID
- `idx_symbol` - 交易对
- `idx_run_time` - 运行时间
- `idx_trades_run_id` - 交易记录
- `idx_equity_run_id` - 净值曲线

### 数据清理

定期清理旧数据：

```python
from src.backtest.storage import BacktestStorage
from datetime import datetime, timedelta

storage = BacktestStorage()

# 删除 90 天前的回测
cutoff = datetime.now() - timedelta(days=90)
old_runs = storage.list_backtests(limit=10000)

for run in old_runs:
    if datetime.fromisoformat(run['run_time']) < cutoff:
        storage.delete_backtest(run['run_id'])
```

## 注意事项

1. **数据完整性** - 确保保存完整的 equity_curve 和 trades 数据
2. **存储空间** - 大量回测会增加数据库大小，建议定期清理
3. **并发访问** - SQLite 支持多读单写，高并发场景考虑 PostgreSQL
4. **备份** - 定期备份 `data/backtest_analytics.db`

## 下一步

- [ ] 实现 Phase 3: 可视化分析页面
- [ ] 实现 Phase 4: 自动参数优化引擎
- [ ] 添加更多分析维度（季节性、市场状态等）
- [ ] 支持多币种联合分析
