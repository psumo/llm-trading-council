# 🤖 Multi-Agent Runtime Architecture

> LLM-TradeBot 当前运行时多 Agent 架构（与 `main.py` 实现对齐）

## 架构总览

系统当前不是单一路径 5-Agent 线性串行，而是“多分支分析 + 决策路由 + 风控闸门 + 单机会执行”。

```text
Symbol Selector (AUTO1/AUTO3)
        │
        ▼
DataSyncAgent ──► QuantAnalystAgent ──┬──► PredictAgent (optional)
                                       ├──► ReflectionAgent (optional)
                                       ├──► Trend/Setup/Trigger Agent (LLM/Local optional)
                                       └──► MultiPeriodParserAgent
                                                │
                                                ▼
                                      Decision Router
                      (Forced Exit / Fast Trend / LLM / Rule-Based DecisionCore)
                                                │
                                                ▼
                                         RiskAuditAgent
                                                │
                                                ▼
                                      Executor (single best open per cycle)
```

## Agent 分层

| 层级 | Agent | 作用 | 是否可选 |
|---|---|---|---|
| 数据层 | DataSyncAgent | 拉取 5m/15m/1h 快照与实时价格 | 否 |
| 分析层 | QuantAnalystAgent | 趋势/震荡/情绪/陷阱信号 | 否 |
| 分析层 | PredictAgent | 30m 概率预测 | 是 |
| 分析层 | ReflectionAgent / ReflectionAgentLLM | 交易复盘，提供 prompt 上下文 | 是 |
| 分析层 | Trend/Setup/Trigger Agent (LLM/Local) | 语义解释与结构化 stance | 是 |
| 汇总层 | MultiPeriodParserAgent | 多周期一致性摘要 | 否 |
| 决策层 | Decision Router | 选择 forced-exit / fast-trend / LLM / rule-based 路径 | 否 |
| 风控层 | RiskAuditAgent | 一票否决、止损修正、保证金/风险检查 | 否 |
| 执行层 | Executor | 执行订单，维护交易/仓位状态 | 否 |

## 周期执行流程

1. 读取 symbols（可由 Selector 动态刷新）。
2. 对每个 symbol 执行分析流程（`analyze_only=True`）：
   - 数据准备与有效性检查
   - 并行分析任务（Quant / Predict / Reflection）
   - Four-Layer Filter + 语义分析 + Multi-Period 汇总
   - 决策路由并过 RiskAudit
3. 收集所有 `suggested` 开仓建议。
4. 仅执行置信度最高的 1 个开仓建议（单周期单开仓上限）。
5. 更新账户、日志、决策历史与可视化状态。

## 决策路由优先级

1. `forced_exit`: 持仓超时/亏损阈值触发强制平仓。  
2. `fast_trend`: 30m 动量快速信号触发。  
3. `llm`: Bull/Bear 并行视角 + LLM 决策。  
4. `decision_core`: LLM 不可用时回退规则决策。  

## 动作协议（统一）

系统统一动作枚举（见 `src/utils/action_protocol.py`）：

- `open_long`
- `open_short`
- `close_long`
- `close_short`
- `wait`
- `hold`

说明：

- 所有外部/内部动作先归一化再进入风控和执行层。
- `close/close_position` 仅作为兼容输入，运行时会映射到明确方向的 close 动作。

## 关键实现文件

- 编排主流程：`/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/main.py`
- Agent 配置：`/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/src/agents/agent_config.py`
- 动作协议：`/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/src/utils/action_protocol.py`
- 分析→执行契约：`/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/src/agents/contracts.py`
- 风控：`/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/src/agents/risk_audit_agent.py`
- 状态与 API：`/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/src/server/state.py`, `/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot/src/server/app.py`

## 扩展建议

1. 新增 Agent 时优先接入 `agent_outputs`，并定义清晰输入/输出 schema。  
2. 新动作必须先扩展 action protocol，再接入风控与执行。  
3. Dashboard 展示字段应来自 `global_state` 的锁保护快照，避免竞态读。  
