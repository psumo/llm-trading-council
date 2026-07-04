# ⚖️ DecisionCoreAgent (The Critic)

> 对抗评论员 - 加权投票与决策融合

## 概述

DecisionCoreAgent 是多 Agent 框架的决策核心，整合来自 QuantAnalystAgent 和 PredictAgent 的多维度信号，通过加权投票机制生成最终交易决策。

## 核心职责

1. **加权投票** - 整合多周期趋势、震荡、情绪和 ML 预测信号
2. **多周期对齐** - 检测 1h/15m/5m 趋势一致性
3. **市场感知** - 集成位置分析和状态检测
4. **对抗审计** - 检测技术信号与资金流背离

## 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                     DecisionCoreAgent                            │
├─────────────────────────────────────────────────────────────────┤
│ 输入：                                                           │
│   - quant_analysis: QuantAnalystAgent 输出                       │
│   - predict_result: PredictAgent 输出                            │
│   - market_data: 原始市场数据                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 信号提取                                                   │   │
│  │ trend_5m/15m/1h, oscillator_5m/15m/1h, sentiment, prophet │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 市场状态分析                                               │   │
│  │ • RegimeDetector: trending/choppy/volatile/unknown        │   │
│  │ • PositionAnalyzer: 价格位置百分比                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 加权投票计算                                               │   │
│  │ weighted_score = Σ(signal × weight)                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 多周期对齐检测                                             │   │
│  │ • 完全对齐: 1h/15m/5m 同向                                 │   │
│  │ • 部分对齐: 1h/15m 同向                                    │   │
│  │ • 不对齐: 多周期分歧                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 对抗式审计                                                 │   │
│  │ • 技术看多 + 机构流出 → 信心衰减 50%                        │   │
│  │ • 技术看空 + 机构流入 → 信心衰减 50%                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
├─────────────────────────────────────────────────────────────────┤
│ 输出：VoteResult                                                 │
│   - action: "long" / "short" / "hold"                           │
│   - confidence: 0 ~ 100                                          │
│   - weighted_score: -100 ~ +100                                  │
│   - multi_period_aligned: bool                                   │
│   - vote_details: 各信号贡献分                                   │
│   - reason: 决策原因                                             │
│   - regime: 市场状态                                             │
│   - position: 价格位置                                           │
└─────────────────────────────────────────────────────────────────┘
```

## 信号权重配置

```python
@dataclass
class SignalWeight:
    # 趋势信号 (合计 0.45)
    trend_5m: float = 0.10
    trend_15m: float = 0.15
    trend_1h: float = 0.20
    
    # 震荡信号 (合计 0.20)
    oscillator_5m: float = 0.05
    oscillator_15m: float = 0.07
    oscillator_1h: float = 0.08
    
    # ML 预测
    prophet: float = 0.15
    
    # 情绪信号 (动态权重)
    sentiment: float = 0.20
```

> **注意**：所有权重合计为 1.0，情绪信号在无数据时权重降为 0

## 关键数据结构

### VoteResult

```python
@dataclass
class VoteResult:
    action: str              # 'long', 'short', 'hold'
    confidence: float        # 0.0 ~ 100.0
    weighted_score: float    # -100 ~ +100
    vote_details: Dict       # 各信号贡献分明细
    multi_period_aligned: bool
    reason: str              # 决策原因说明
    regime: Optional[Dict]   # 市场状态
    position: Optional[Dict] # 价格位置
```

## 决策阈值

| 条件 | 动作 | 信心度 |
|------|------|--------|
| score > 50 && aligned | long | 85% |
| score > 30 | long | 60-75% |
| score < -50 && aligned | short | 85% |
| score < -30 | short | 60-75% |
| 其他 | hold | 根据得分 |

## 过滤逻辑

### 市场状态过滤

```python
if regime == 'choppy' and position == 'middle':
    return "禁止开仓: 震荡市且价格处于区间中部"
```

### 对抗式审计

```python
# 技术信号与资金流背离检测
if action == 'open_long' and inst_netflow_1h < -1000000:
    confidence *= 0.5  # 看多但机构流出，信心减半
```

## 辅助分析器

### RegimeDetector (市场状态检测)

| 状态 | 说明 | 条件 |
|------|------|------|
| trending | 趋势市 | ADX > 25, EMA 对齐 |
| choppy | 震荡市 | ADX < 20, 价格在均线附近 |
| volatile | 高波动 | ATR/Price > 阈值 |
| unknown | 不明确 | 以上都不满足 |

### PositionAnalyzer (价格位置分析)

```python
position_pct = (current_price - min) / (max - min) * 100
# 0% = 区间最低, 100% = 区间最高

location = "bottom" if pct < 30 else "top" if pct > 70 else "middle"
allow_long = pct < 70   # 高位禁止做多
allow_short = pct > 30  # 低位禁止做空
```

## 依赖关系

```
DecisionCoreAgent
├── SignalWeight (权重配置)
├── PositionAnalyzer (src/agents/position_analyzer.py)
├── RegimeDetector (src/agents/regime_detector.py)
└── VoteResult (输出结构)
```

## 使用示例

```python
from src.agents.decision_core_agent import DecisionCoreAgent

agent = DecisionCoreAgent()
result = await agent.make_decision(
    quant_analysis=quant_output,
    predict_result=predict_output,
    market_data=market_data
)

print(f"决策: {result.action}")
print(f"信心: {result.confidence}%")
print(f"加权得分: {result.weighted_score}")
print(f"多周期对齐: {result.multi_period_aligned}")
```

## 日志输出

Dashboard 日志格式：

```
⚖️ DecisionCoreAgent (The Critic): Context(Regime=choppy, Pos=27%) => Vote: WAIT ([CHOPPY] | 加权得分: -17.2 | 周期对齐: 多周期分歧(1h:-1, 15m:0, 5m:0) | sentiment: -50 | trend_1h: -40)
```
