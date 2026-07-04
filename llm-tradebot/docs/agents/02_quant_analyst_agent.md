# 👨‍🔬 QuantAnalystAgent (The Strategist)

> 量化策略师 - 多维度市场信号分析

## 概述

QuantAnalystAgent 是多 Agent 框架的分析引擎，由三个子 Agent 组成，分别负责趋势、震荡和情绪分析，输出标准化的量化得分供决策层使用。

## 核心职责

1. **趋势分析** - 基于 EMA/MACD 计算多周期趋势得分
2. **震荡分析** - 基于 RSI 检测超买超卖状态
3. **情绪分析** - 整合资金流、资金费率、OI 等市场情绪指标
4. **综合评估** - 加权汇总生成综合市场得分

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    QuantAnalystAgent                             │
├─────────────────────────────────────────────────────────────────┤
│ 输入：MarketSnapshot (来自 DataSyncAgent)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │TrendSubAgent │  │OscillatorSub │  │SentimentSub  │          │
│  │  (趋势分析)   │  │  (震荡分析)   │  │  (情绪分析)   │          │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤          │
│  │ • EMA 金叉    │  │ • RSI 超买    │  │ • 资金流      │          │
│  │ • MACD 动量   │  │ • RSI 超卖    │  │ • 资金费率    │          │
│  │ • 实时修正    │  │ • 多周期 RSI  │  │ • OI 变化     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│        │                  │                  │                  │
│        └──────────────────┴──────────────────┘                  │
│                           │                                      │
│                    综合加权得分                                   │
│             (趋势40% + 震荡30% + 情绪30%)                         │
├─────────────────────────────────────────────────────────────────┤
│ 输出：quant_analysis Dict                                        │
│   - trend: 趋势分析结果                                          │
│   - oscillator: 震荡分析结果                                     │
│   - sentiment: 情绪分析结果                                      │
│   - comprehensive: 综合评估                                      │
└─────────────────────────────────────────────────────────────────┘
```

## 子 Agent 详解

### TrendSubAgent (趋势分析员)

**得分逻辑**（-100 ~ +100）：

- 1h EMA 金叉 → +40 分 (主趋势)
- 15m MACD 扩大 → ±30 分 (中期确认)
- 实时 K 线修正 → ±20 分 (短期动量)

**输出字段**：

```python
{
    'score': int,                # 总得分
    'trend_1h_score': int,       # 1h 趋势得分
    'trend_15m_score': int,      # 15m 趋势得分
    'trend_5m_score': int,       # 5m/实时修正得分
    'details': {
        '1h_trend': str,         # "上涨" / "下跌"
        '1h_ema12': float,
        '1h_ema26': float,
        '15m_trend': str,
        '15m_macd_diff': float,
        'live_correction': str
    }
}
```

### OscillatorSubAgent (震荡分析员)

**得分逻辑**：

- RSI > 75 → -80 (超买严重)
- RSI < 25 → +80 (超卖严重)
- 权重：5m 30%, 15m 30%, 1h 40%

**输出字段**：

```python
{
    'score': int,
    'osc_5m_score': int,
    'osc_15m_score': int,
    'osc_1h_score': int,
    'rsi_5m': float,          # 供 dashboard 显示
    'rsi_15m': float,
    'rsi_1h': float,
    'details': {...}
}
```

### SentimentSubAgent (情绪分析员)

**数据源**：

1. **机构资金流** - 来自外部量化 API
2. **资金费率** - Binance 原生数据 (逆向指标)
3. **OI 变化率** - 来自 OITracker 历史追踪

**得分逻辑**：

- 机构净流入 1h > 0 → +30 分
- 资金费率 > 0.03% → -30 分 (多头拥挤)
- OI 24h 变化 > 10% → +10 分 (市场活跃)

**输出字段**：

```python
{
    'score': int,
    'oi_change_24h_pct': float,   # 24h OI 变化率
    'total_sentiment_score': int,
    'details': {
        'inst_netflow_1h': float,
        'binance_funding_rate': float,
        'funding_signal': str,
        'binance_oi_value': float
    }
}
```

## 综合评估

```python
composite_score = (trend * 0.4) + (oscillator * 0.3) + (sentiment * 0.3)
```

信号映射：

- score > 30 → "buy"
- score < -30 → "sell"
- else → "neutral"

## 依赖关系

```
QuantAnalystAgent
├── TrendSubAgent
├── OscillatorSubAgent
├── SentimentSubAgent
│   └── OITracker (src/utils/oi_tracker.py)
└── MarketSnapshot (来自 DataSyncAgent)
```

## 使用示例

```python
from src.agents.quant_analyst_agent import QuantAnalystAgent

agent = QuantAnalystAgent()
analysis = await agent.analyze_all_timeframes(snapshot)

# 访问各维度得分
trend_score = analysis['trend']['score']
oscillator_score = analysis['oscillator']['score']
sentiment_score = analysis['sentiment']['score']
composite = analysis['comprehensive']['score']
```

## 日志输出

Dashboard 日志格式：

```
👨‍🔬 QuantAnalystAgent (The Strategist): Trend(上涨,-40) | Osc(RSI:43,0) | Sent(OI:0.1%,-10) => Score: -19/100
```
