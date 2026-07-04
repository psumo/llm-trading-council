# LLM Trading Council

Three AI traders debate every crypto candle. An LLM judge makes the call. Every decision gets paper traded and scored after fees.

This is a confluence system: independent signals only become a trade when they line up, and a judge with a real methodology decides when that is. It's also a measurement rig. The point isn't "this bot makes money". The point is finding out whether AI signal fusion has any edge at all, with numbers you can't fudge.

```
                 +----------------------------------------------+
                 |              THE COUNCIL                     |
                 |                                              |
   charts  --->  |  LLM Chart Analyst   (Gemini, ~80 indicators)|
   klines  --->  |  Multi-Agent Quant   (trend/setup/ML)        |
   trades  --->  |  Order-Flow Engine   (footprints + delta)    |
                 +----------------------+-----------------------+
                                        |  votes + full context
                                        v
                 +----------------------------------------------+
                 |  THE JUDGE (LLM, structured output)          |
                 |  regime -> permission -> score -> trigger    |
                 |  separates "enter now" from "stay flat"      |
                 |  outputs entry / stop / targets / win prob   |
                 +----------------------+-----------------------+
                                        v
                 +----------------------------------------------+
                 |  GUARDS (independent risk vetoes)            |
                 |  opposition check, stop-distance floor,      |
                 |  loss cooldown, daily circuit breaker        |
                 +----------------------+-----------------------+
                                        v
                 +----------------------------------------------+
                 |  PAPER TRACKER + JOURNAL                     |
                 |  fee-adjusted R, win rate that can't lie,    |
                 |  per-voice scorecards, self-written lessons  |
                 +----------------------------------------------+
```

## Why this exists

Most AI trading repos have two problems. They never measure themselves properly, and they either demand all signals agree (so they never trade) or follow one signal blindly (so they get chopped up). This project went through both failure modes and has the commit history to prove it.

What came out the other side:

**Accounting that can't lie to you.** Early on, the tracker showed a 100% win rate while the account was down money. The judge had set a take-profit so close to entry that the "win" was smaller than the trading fee. Now every R-multiple is net of fees, wins are classified by realized PnL instead of which level got hit, and the tracker recomputes risk:reward from actual levels instead of trusting what the judge claims. If the win rate and equity curve ever disagree again, that's a bug.

**Fusion instead of unanimity.** Requiring three signals to all agree multiplies their pass rates together and you basically never trade (this is just Grinold-Kahn: information ratio scales with the square root of breadth). Here the trend voices grant permission, setup quality is a score, and order flow times the entry. A voice can only veto when it actively opposes the trade.

**A system that studies its own losses.** A reflection loop reads the trade journal and writes lessons into the judge's next prompt. Its first ever self-written lesson: "when only 1 voice agrees, 4 out of 4 trades lost." It was right, and that rule became a hard guard.

Everything lands in an append-only journal: judge verdicts, guard blocks, skipped entries, per-voice hit rates. You can audit every decision the system ever made.

## What's inside

| Component | What it does | Where it came from |
|---|---|---|
| `aggregator/` | The core. Judge fusion, guard pipeline, paper tracker, voice scorecards, reflection loop, dashboard. ~90 tests. | Original code, this repo |
| `llm-trader/` | Chart analyst voice. Renders candlesticks, computes ~80 indicators, gets a structured verdict from Gemini | MIT fork of [qrak/LLM_trader](https://github.com/qrak/LLM_trader), patched |
| `llm-tradebot/` | Quant voice. Trend/setup/trigger agents, 4-layer filter, LightGBM predictor | MIT fork of [EthanAlgoX/LLM-TradeBot](https://github.com/EthanAlgoX/LLM-TradeBot), crash fixes included |
| `orderflow/` | Order-flow voice. Footprint candles, stacked bid/ask imbalances, delta, from live exchange trades into TimescaleDB | MIT fork of [focus1691/orderflow](https://github.com/focus1691/orderflow), WebSocket layer rewritten |

Fork provenance is in [`VENDOR.md`](VENDOR.md). Every local patch is a reviewable diff in [`vendor-patches/`](vendor-patches/).

## Quickstart

Windows-first for now (the ops scripts are PowerShell, the code itself is portable). You need Python 3.13+, Node 18+, Docker for TimescaleDB, and a [Gemini API key](https://aistudio.google.com/). The free tier works.

```bash
git clone https://github.com/psumo/llm-trading-council
cd llm-trading-council

# 1. Configure the aggregator
cd aggregator
cp config.example.yaml config.yaml     # replace <STACK_ROOT> with your clone path
uv venv && uv pip install -r requirements.txt
python -m pytest tests/ -q             # ~90 tests should pass

# 2. Give each voice its API keys (templates provided in each dir)

# 3. Launch (detached background processes, health checks included)
cd ..
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
powershell -ExecutionPolicy Bypass -File .\status.ps1
# dashboard at http://localhost:8500
```

`stop-all.ps1` shuts everything down, including the headless Chromium instances the chart renderer spawns. Ask us how we learned that one.

## The dashboard

One dark terminal view at `localhost:8500`. Account strip with equity sparkline up top, then per-symbol signal tiles where the judge's verdict is the big colored element, then the full trade ticket (entry, stop, targets, rationale, invalidation, where the voices disagree), then each voice's complete reasoning, then the journal and lessons.

## Read this before you get excited

This is not financial advice and it is not a money printer. In our own forward tests the system was appropriately picky and still ended slightly negative after fees, on a sample too small to mean anything. That's the honest state of it. The interesting question is whether your configuration of voices and judge can beat that, measurably.

Paper trading only. Fills are simulated at level prices with a configurable fee model. There is deliberately no live order execution in this repo.

For context: in the only public real-money LLM trading benchmark to date, most frontier models lost money. This repo exists to measure that kind of claim, not to make one.

## Contributing

The architecture is pluggable on purpose. A "voice" is anything that can answer a poll with a direction, a confidence, and its reasoning. Write one class and the scorecard system starts grading your signal against the incumbents automatically, hit rate and all. Bring a signal, leave with a track record.

Good entry points, roughly in order of value:

- **Add a voice.** Funding-rate skew, liquidation cascades, open interest, sentiment, on-chain flows, your own model. One class, see [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Improve the judge.** The prompt encodes a five-check intraday methodology. Changes show up in the journal, so prompt claims come with evidence.
- **Add a guard.** ~15 lines for a new risk veto.
- **Port the ops scripts to Linux/macOS.** Most wanted PR by far.
- **Submit receipts.** Run it, post your journal stats in Discussions. Negative results welcome, that's the whole ethos.

Merged contributors go in the hall of fame below. Contributed voices keep their author's name on the scorecard.

## License

MIT for the original code here (see [`LICENSE`](LICENSE)). The three vendored voices keep their upstream MIT licenses and copyrights.
