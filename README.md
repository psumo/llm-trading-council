# ⚖️ LLM Trading Judge

### Three AI traders argue. An LLM judge decides. Every trade gets honestly scored.

**An open-source signal-fusion lab for crypto: an LLM chart analyst, a multi-agent quant bot, and a real-time order-flow engine each form an independent opinion — then a calibrated LLM judge fuses them into one decision, a guard pipeline can veto it, and a fee-honest paper tracker keeps the receipts.**

No hype, no "this bot prints money." The whole point of this project is the opposite: **a rig for finding out — honestly — whether AI signal fusion has any edge at all.** It logs every decision, scores every voice, deducts fees from every R-multiple, and even writes its own post-mortem lessons that feed back into the judge's next prompt.

```
                 ┌──────────────────────────────────────────────┐
                 │             THE THREE VOICES                 │
                 │                                              │
   charts ────►  │  🧠 LLM Chart Analyst  (Gemini + 80 indics)  │
   klines ────►  │  🤖 Multi-Agent Quant  (trend/setup/ML)      │
   trades ────►  │  📊 Order-Flow Engine  (footprints + delta)  │
                 └──────────────────┬───────────────────────────┘
                                    │  votes + full context (multi-timeframe)
                                    ▼
                 ┌──────────────────────────────────────────────┐
                 │  ⚖️ THE JUDGE  (LLM, structured output)      │
                 │  regime router → permission → score → trigger │
                 │  entry_conviction ≠ flat_confidence           │
                 │  emits: entry / stop / targets / win-prob     │
                 └──────────────────┬───────────────────────────┘
                                    ▼
                 ┌──────────────────────────────────────────────┐
                 │  🛡️ GUARDS   (independent risk vetoes)       │
                 │  opposition check · stop-distance floor       │
                 │  loss cooldown · daily circuit breaker        │
                 └──────────────────┬───────────────────────────┘
                                    ▼
                 ┌──────────────────────────────────────────────┐
                 │  📒 PAPER TRACKER + JOURNAL                  │
                 │  fee-adjusted R · net-R win/loss · scorecards │
                 │  reflection loop writes lessons → judge memory│
                 └──────────────────────────────────────────────┘
```

## Why this exists

Most "AI trading bot" repos share two sins: they never measure themselves honestly, and they collapse the moment one component disagrees. This project was built the other way around:

- **Honest accounting is the product.** A take-profit hit whose reward is smaller than the round-trip fee is recorded as a **loss** (we found that bug the hard way — "100% win rate, negative return"). R-multiples are net of fees. Win rate can never contradict the equity curve.
- **Fusion beats unanimity.** Requiring all signals to agree multiplies their pass-rates into near-zero trade frequency (Grinold–Kahn: `IR = IC × √breadth`). Here trend grants *permission*, setup quality is a *score*, order flow is a *timing trigger* — and a disagreeing voice can veto only when it actively opposes.
- **The system studies its own losses.** A reflection loop mines the trade journal and writes conditional lessons ("when only 1 voice agrees, 4/4 trades lost") straight into the judge's prompt. Its first self-written lesson was correct.
- **Everything is a receipt.** Judge verdicts, guard blocks, skipped entries, voice scorecards — all in an append-only journal you can audit.

## What's inside

| Component | What it is | Origin |
|---|---|---|
| `aggregator/` | The core: judge fusion, guard pipeline, paper tracker, per-voice scorecards, reflection loop, full-viewport dashboard. ~90 tests. | **Original code (this repo)** |
| `llm-trader/` | LLM chart analyst voice — renders candlestick charts, computes ~80 indicators, asks Gemini for a structured verdict | MIT fork of [qrak/LLM_trader](https://github.com/qrak/LLM_trader) + our patches |
| `llm-tradebot/` | Multi-agent quant voice — trend/setup/trigger agents, 4-layer filter, LightGBM predictor | MIT fork of [EthanAlgoX/LLM-TradeBot](https://github.com/EthanAlgoX/LLM-TradeBot) + our crash fixes |
| `orderflow/` | Footprint-candle engine — stacked bid/ask imbalances + delta from live exchange trades (TimescaleDB) | MIT fork of [focus1691/orderflow](https://github.com/focus1691/orderflow) + native-WebSocket rewrite |

See [`VENDOR.md`](VENDOR.md) for exact fork provenance and [`vendor-patches/`](vendor-patches/) for every local patch as a reviewable diff.

## Quickstart

> **Windows-first** (the ops scripts are PowerShell); the Python/TS code itself is portable. You'll need: Python 3.13+, Node 18+, Docker (TimescaleDB), a [Gemini API key](https://aistudio.google.com/) (the free tier works).

```bash
git clone https://github.com/psumo/llm-trading-judge
cd llm-trading-judge

# 1. Configure the aggregator
cd aggregator
cp config.example.yaml config.yaml     # then replace <STACK_ROOT> with your clone path
uv venv && uv pip install -r requirements.txt
python -m pytest tests/ -q             # ~90 tests should pass

# 2. Configure the voices (each has its own .env.example / keys template)
#    - llm-trader:  keys.env  (GOOGLE_STUDIO_API_KEY=...)
#    - llm-tradebot: .env     (GEMINI_API_KEY=...)
#    - orderflow:   .env      (DB_URL=..., SYMBOLS=BTCUSDT)

# 3. Launch everything (detached background processes + health checks)
cd ..
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
powershell -ExecutionPolicy Bypass -File .\status.ps1
# dashboard → http://localhost:8500
```

`stop-all.ps1` tears everything down cleanly (including sweeping the chart-render Chromium processes — ask us how we know).

## The dashboard

One dark, full-viewport terminal at `localhost:8500`: account strip with equity sparkline → per-symbol signal tiles (judge verdict as the dominant visual, conviction bar, timeframe alignment) → the judge's full trade ticket with rationale, invalidation and disagreements → each voice's complete reasoning → journal, lessons, and event log.

## Honest disclaimers (read these)

- **This is not financial advice and not a money printer.** In our own forward tests the system was *correctly selective and still slightly net-negative after fees* on a tiny sample. That's the honest state of the art — the interesting question is whether *your* voice/judge configuration can do better, measurably.
- **Paper trading only.** The tracker simulates fills at level prices with a configurable fee model. There is deliberately **no live order execution** in this repo.
- LLM trading is unproven territory: in the only public real-money LLM trading benchmark, most frontier models lost money. This repo exists to measure, not to promise.

## Contributing — the Voice Arena 🏟️

The architecture is deliberately pluggable: **a "voice" is anything that can emit `{direction, confidence, detail, extra}` on a poll.** The most valuable contribution is a new voice — sentiment, funding-rate skew, liquidation cascades, on-chain flows, your own model — and the journal + scorecards will grade it against the incumbents with zero extra work.

Ways to contribute (see [`CONTRIBUTING.md`](CONTRIBUTING.md)):
- 🎙️ **Add a voice** — implement one class, get scored on the per-voice scorecard
- 🧑‍⚖️ **Improve the judge** — prompt engineering with measurable consequences (every change shows up in the journal)
- 🛡️ **Add a guard** — one ~15-line class with a `check(ctx) -> reason | None`
- 📒 **Submit receipts** — run the stack, share your journal stats (win rate, avg net R, profit factor) in a Results discussion; reproducible configs beat opinions
- 🐧 **Port the ops scripts to Linux/macOS** — the single most-wanted PR

Every merged contributor goes in the README hall of fame, and every contributed voice gets a standing scorecard entry named after its author. Bring a signal; leave with a track record.

## License

MIT for the original code in this repo (see [`LICENSE`](LICENSE)). The three vendored components retain their upstream MIT licenses and copyrights — see each subdirectory's `LICENSE` and [`VENDOR.md`](VENDOR.md).
