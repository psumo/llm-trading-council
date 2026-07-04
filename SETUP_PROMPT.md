# Agent setup prompt

Using Claude Code, Cursor, Codex, or any other coding agent? Paste everything below the line into it and it will set the whole stack up for you, asking you only for the things it genuinely needs (your Gemini API key and which symbol to trade).

---

You are setting up the LLM Trading Council stack (https://github.com/psumo/llm-trading-council) for me on this machine. It is a paper-trading signal-fusion system: three signal services plus an aggregator with an LLM judge. Nothing in it places real orders. Work through the steps below in order, verify each one before moving on, and ask me only when a step genuinely needs my input. Report what you did at the end, including anything that failed.

Ground rules:
- Never commit, print, or log my API keys. They go into local env files only, and those files are gitignored.
- If a step fails, stop and diagnose it rather than skipping ahead. The stack has hard dependencies between steps.
- This repo is Windows-first. If I am on Linux or macOS, the Python and Node services all still run, but the three PowerShell ops scripts (start-all.ps1, stop-all.ps1, status.ps1) need shell equivalents. Write them as part of setup and tell me you did.

Step 0. Prerequisites check.
Verify and report versions: Python 3.13+, Node 18+, Docker (daemon running), git, and either uv (preferred) or pip. If uv is missing, install it or fall back to python -m venv + pip. Ask me for my Gemini API key now (I can get a free one at https://aistudio.google.com/) and ask which symbol I want to trade (default BTCUSDT). You need the key twice in later steps.

Step 1. Clone.
git clone https://github.com/psumo/llm-trading-council and cd into it. All paths below are relative to the repo root. Where a config wants an absolute path, compute it from where I cloned.

Step 2. The aggregator (the core service).
- cd aggregator
- Create a venv and install deps: uv venv then uv pip install -r requirements.txt (note: uv venvs have no pip module inside them, so always use uv pip, not python -m pip).
- cp config.example.yaml config.yaml, then replace every <STACK_ROOT> in config.yaml with the absolute path of the repo root, forward slashes even on Windows.
- In config.yaml, set the instrument symbol to the one I chose.
- Run the tests: python -m pytest tests/ -q using the venv's python. Around 90 tests should pass. If any fail, stop and show me.

Step 3. TimescaleDB (order-flow storage).
- cd orderflow
- docker compose -f docker-compose.db.yml up -d
- Verify: docker ps shows a container named confluence_orderflow_db, and port 5455 on localhost accepts connections. The default credentials are postgres/password and the container binds to 127.0.0.1 only. That is intentional for a local dev database.

Step 4. The order-flow collector (Node/NestJS).
- Still in orderflow: create its env file by copying config.confluence.txt to a file named .env in that directory. Set SYMBOLS to my symbol and make sure DB_URL points at localhost:5455.
- yarn install (the repo uses yarn, there is a yarn.lock).
- yarn build:okx
- Smoke test: node dist/apps/okx/main.js should log a websocket connection within ~15 seconds, then Ctrl+C it (the launcher runs it properly later). If my symbol does not exist as an OKX USDT perpetual, tell me and suggest alternatives.

Step 5. The LLM chart analyst (llm-trader).
- cd llm-trader
- uv venv then uv pip install -r requirements.txt. This one is heavy (torch, chromadb, sentence-transformers); expect several minutes.
- Copy keys.env.example to keys.env and put my Gemini key in GOOGLE_STUDIO_API_KEY.
- Copy config/config.ini.example to config/config.ini if config.ini does not already exist. Set crypto_pair to my symbol in ccxt perpetual form (BTCUSDT becomes BTC/USDT:USDT), timeframe = 5m, and google_studio_model = gemini-3.5-flash (flash keeps API costs low; this bot calls the model every candle).
- Know this gotcha: the chart renderer (plotly/kaleido) drives a headless Chromium per render. Roughly 15 to 20 chromium processes while it is analyzing is normal, not a leak. The repo's stop script sweeps them.

Step 6. The multi-agent quant bot (llm-tradebot).
- cd llm-tradebot
- uv venv then uv pip install -r requirements.txt.
- Copy .env.example to .env. Set GEMINI_API_KEY to my key, TRADING_SYMBOLS to my symbol, and LLM_MODEL=gemini-3.5-flash.
- In config.yaml set symbols to a list containing my symbol and primary_symbol to it.
- It runs in paper mode with a virtual account. On Windows the launcher run-paper.ps1 already sets PORT=8001 and AUTO_START=true; on other platforms export those env vars in the launcher you write.

Step 7. Launch and verify.
- On Windows: powershell -ExecutionPolicy Bypass -File .\start-all.ps1 from the repo root, then .\status.ps1. On other platforms use the launcher you wrote; the services and ports are: TimescaleDB 5455, orderflow collector 3000, llm-trader dashboard 8000, llm-tradebot dashboard 8001, aggregator 8500.
- Give it 2 to 3 minutes (the analyst loads models on first boot), then verify:
  - http://localhost:8500/api/health responds
  - http://localhost:8500/api/state shows all three voices reporting (direction values that are not all "offline")
  - the dashboard renders at http://localhost:8500
- The first judge verdict appears within about 5 minutes. FLAT with a written rationale is a healthy first verdict, not a failure; the judge is designed to be picky.

Step 8. Report.
Tell me: versions found, what you set up, test results, which voices are online, the first judge verdict, and how to stop everything (stop-all.ps1 or your equivalent). Remind me where my keys live and that they are gitignored.

Common failure modes, so you do not rediscover them:
- Aggregator says a voice is offline: that voice's service is down or its env file is missing a key. Check the per-service logs in logs/.
- Order-flow voice offline with "no footprint rows": the collector is not writing. Check the container is up and the collector process is running; some exchanges' websockets are geo-blocked on some networks, in which case try a VPN or a different symbol.
- llm-trader analysis hangs: usually the Gemini free tier rate-limiting a stalled connection. The client has a 180s timeout and retries; if it persists, wait out the rate limit or use a paid key.
- Windows toasts fail on Linux/macOS: expected, notifications degrade silently; everything else works.
