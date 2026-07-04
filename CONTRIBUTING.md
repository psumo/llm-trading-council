# Contributing to LLM Trading Council

Claims are cheap. Journals are receipts. That's the premise here. Every contribution below is designed so its value is measurable by the system itself.

## The highest-value contribution: add a Voice

A voice is any signal source that can answer a poll with a `Vote`:

```python
# aggregator/sources/base.py defines the contract
Vote(
    source="my_funding_skew_voice",
    direction="long" | "short" | "neutral" | "offline",
    confidence=0.0..1.0,
    age_seconds=...,      # how fresh the underlying data is
    detail="one-line human-readable reasoning",
    extra={...},          # full context, shown on the dashboard, fed to the judge
)
```

Steps:
1. Copy the shape of `aggregator/sources/orderflow.py` (the simplest voice).
2. Implement `poll() -> Vote`. Degrade to `offline(...)` on any failure, a voice must never crash the loop.
3. Register it in `instrument.py` and add it to `voices` in `config.example.yaml`.
4. Add tests (see `tests/test_orderflow_multitf.py` for the pattern).

The moment your voice runs, the **per-voice scorecard** starts grading it against real price moves (hit rate over a resolution horizon, per-regime splits), your signal gets a public, automatic track record. Voice ideas we'd love: funding-rate skew, liquidation cascades, open-interest divergence, cross-exchange basis, news/sentiment, on-chain flows.

## Improve the Judge

The judge prompt lives in `aggregator/judge_prompt.py` (`_SYSTEM_PREAMBLE`). It encodes a five-check intraday methodology (regime → higher-TF bias → trigger → flow confirmation → risk). Prompt changes are measurable: run the stack, and the journal shows exactly how decisions shifted. PRs that change the prompt should include before/after journal excerpts.

## Add a Guard

Guards are independent pre-execution vetoes, ~15 lines each:

```python
@dataclass(frozen=True)
class MyGuard:
    name: str = "my_guard"
    def check(self, ctx: GuardContext) -> str | None:
        return None            # allow
        # or: return "reason"  # block (logged as POSITION_BLOCKED with the reason)
```

See `aggregator/guards.py`. Guards fail SAFE (an exception blocks the trade). Ideas: session filter, funding-window avoidance, volatility-percentile floor, news-blackout.

## Submit Receipts (no code required)

Run the stack on any pair/config for a meaningful stretch and post your results in **Discussions → Results**: config diff, number of trades, win rate, average net R, profit factor, max drawdown (all shown on the dashboard / `/api/journal`). Reproducible negative results are as welcome as positive ones, this is a measurement project.

## Most-wanted PRs

- **Linux/macOS ops scripts** (the stack itself is portable; `start-all.ps1`/`stop-all.ps1`/`status.ps1` are Windows PowerShell)
- Backtest harness for the judge (replay footprints + candles through the fusion layer)
- More exchanges in the orderflow collector (Bybit/OKX apps exist upstream; wiring + testing needed)
- Live-execution adapter behind an explicit opt-in flag (currently paper-only by design)

## Recognition

- Every merged contributor is added to the README hall of fame.
- Contributed voices keep their author's name in the scorecard (`source="funding_skew (by @you)"` is encouraged).
- Substantial contributions (a new voice with tests, the Linux port, the backtester) get maintainer status offers.

## Ground rules

- Tests must pass: `cd aggregator && python -m pytest tests/ -q`
- No secrets in code or fixtures, API keys come from env files (gitignored).
- Honest accounting is non-negotiable: anything touching PnL/win-rate math needs tests proving win rate can't contradict the equity curve.
- Vendored dirs (`llm-trader/`, `llm-tradebot/`, `orderflow/`), prefer upstreaming fixes to the original projects; patch here only for stack integration.
