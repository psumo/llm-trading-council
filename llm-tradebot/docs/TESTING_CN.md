# LLM-TradeBot 测试指南（小白版）

## 1. 先记住这三条

1. 永远先跑测试模式，不要直接实盘。
2. 每次改代码后先跑自动测试，再启动机器人。
3. 测试通过不代表必赚，只代表“代码没有明显坏掉”。

## 2. 一键测试（推荐）

在项目根目录执行：

```bash
python3 scripts/run_tests.py
```

预期结果类似：

```text
82 passed, 1 skipped
```

说明：

- `passed` 是通过的测试数量。
- `skipped` 是跳过的测试（通常因为本地没启动 Dashboard 服务）。

## 3. 只测某个模块（更快）

```bash
python3 scripts/run_tests.py -q tests/test_agent_config.py
```

## 4. 启动一次安全烟雾测试（不下实盘）

```bash
python3 main.py --test --headless --mode once
```

如果返回码是 `0`，并且日志里没有 `Traceback`，基本说明主流程可运行。

## 5. 常见失败与处理

### 情况 A：`Connection refused`（localhost:8000）

原因：某些测试依赖本地 Web 服务，但你没启动。

处理：

1. 这是正常情况，测试会自动 skip，不影响主测试结果。
2. 如果你要验证 UI 接口，再单独启动服务后重跑。

### 情况 B：`ModuleNotFoundError` 或依赖错误

处理：

```bash
pip install -r requirements.txt
pip install pytest
```

然后重跑：

```bash
python3 scripts/run_tests.py
```

### 情况 C：测试通过但运行时告警

建议先记录告警，再逐步清理；优先处理会导致下单错误、风控失效、进程崩溃的告警。

## 6. 你每天可以照做的节奏

1. `python3 scripts/run_tests.py`
2. `python3 main.py --test --headless --mode once`
3. 看日志是否异常，再决定是否继续长时间测试模式
