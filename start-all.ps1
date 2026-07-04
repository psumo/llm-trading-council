# =====================================================
# start-all.ps1 — bring up the whole confluence stack (detached)
# =====================================================
# Components run as HIDDEN background processes with output redirected to
# logs\<name>.log — they do NOT depend on console windows staying open.
# (Console-window launches kept dying when their terminal/process tree went
# away; this launcher survives terminal closes and Claude sessions.)
#
#   1. orderflow TimescaleDB container (confluence_orderflow_db)
#   2. orderflow OKX collector  -> logs\orderflow.log
#   3. LLM_trader  (port 8000)  -> logs\llm-trader.log
#   4. LLM-TradeBot (port 8001) -> logs\llm-tradebot.log  (AUTO_START=true)
#   5. Aggregator   (port 8500) -> logs\aggregator.log
#
# Usage:   powershell -ExecutionPolicy Bypass -File .\start-all.ps1
# Status:  .\status.ps1        Stop: .\stop-all.ps1
# =====================================================
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Path $logs -Force | Out-Null

function Start-Detached($name, $workdir, $exe, $argList, $envVars = @{}) {
    $existing = $null
    switch ($name) {
        "llm-trader"      { $existing = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) }
        "llm-trader-eth"  { $existing = (Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue) }
        "llm-trader-sol"  { $existing = (Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue) }
        "llm-trader-spcx" { $existing = (Get-NetTCPConnection -LocalPort 8004 -State Listen -ErrorAction SilentlyContinue) }
        "llm-tradebot" { $existing = (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) }
        "aggregator"   { $existing = (Get-NetTCPConnection -LocalPort 8500 -State Listen -ErrorAction SilentlyContinue) }
        "orderflow"    { $existing = (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) }
    }
    if ($existing) { Write-Host "  -> $name already running, skipped" -ForegroundColor Yellow; return }

    foreach ($k in $envVars.Keys) { [Environment]::SetEnvironmentVariable($k, $envVars[$k], "Process") }
    $log = Join-Path $logs "$name.log"
    $proc = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $workdir `
        -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
    foreach ($k in $envVars.Keys) { [Environment]::SetEnvironmentVariable($k, $null, "Process") }
    Write-Host "  -> $name started (pid $($proc.Id), log: logs\$name.log)" -ForegroundColor Green
}

Write-Host "=== Starting confluence stack (detached) ===" -ForegroundColor Cyan

Write-Host "[1/5] orderflow TimescaleDB container..." -ForegroundColor Cyan
$compose = Join-Path $root "orderflow\docker-compose.db.yml"
docker compose -f $compose start 2>$null
if ($LASTEXITCODE -ne 0) { docker compose -f $compose up -d }

Write-Host "[2/5] orderflow OKX collector..." -ForegroundColor Cyan
Start-Detached "orderflow" (Join-Path $root "orderflow") "node" @("dist\apps\okx\main.js")

Write-Host "[3/5] LLM_trader BTC (port 8000)..." -ForegroundColor Cyan
Start-Detached "llm-trader" (Join-Path $root "llm-trader") `
    (Join-Path $root "llm-trader\.venv\Scripts\python.exe") @("start.py") @{ PYTHONUTF8 = "1" }

# Additional single-pair LLM_trader instances sharing the llm-trader repo code +
# .venv. Each runs with CWD = its instance dir (isolates data/cache) and
# LLM_TRADER_HOME = its instance dir (loader reads that dir's config/keys).
$traderVenv = Join-Path $root "llm-trader\.venv\Scripts\python.exe"
$traderStart = Join-Path $root "llm-trader\start.py"
$instRoot = Join-Path $root "llm-trader-instances"
foreach ($inst in @()) {  # per-pair extra instances retired (BTC-only focus)
    $instHome = Join-Path $instRoot $inst.Dir
    Write-Host ("[3+] LLM_trader {0} (port {1})..." -f $inst.Pair, $inst.Port) -ForegroundColor Cyan
    Start-Detached $inst.Name $instHome $traderVenv @($traderStart) `
        @{ PYTHONUTF8 = "1"; LLM_TRADER_HOME = $instHome }
}

Write-Host "[4/5] LLM-TradeBot (port 8001)..." -ForegroundColor Cyan
Start-Detached "llm-tradebot" (Join-Path $root "llm-tradebot") `
    (Join-Path $root "llm-tradebot\.venv\Scripts\python.exe") `
    @("main.py", "--test", "--mode", "continuous", "--interval", "5") `
    @{ PYTHONUTF8 = "1"; PYTHONIOENCODING = "utf-8"; PORT = "8001"; AUTO_START = "true" }

Write-Host "[5/5] Confluence aggregator (port 8500)..." -ForegroundColor Cyan
Start-Detached "aggregator" (Join-Path $root "aggregator") `
    (Join-Path $root "aggregator\.venv\Scripts\python.exe") @("main.py")

# Continuous Chromium reaper: caps the kaleido/Playwright chart-render browsers
# the llm_trader bot leaks. Idempotent -- skip if one is already looping.
$reaperRunning = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '-File .*reap-browsers\.ps1' }
if (-not $reaperRunning) {
    Write-Host "[+] Chromium reaper (background)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", (Join-Path $root "reap-browsers.ps1")
    ) -WindowStyle Hidden | Out-Null
} else {
    Write-Host "  -> reaper already running, skipped" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Stack launched (all hidden/detached) ===" -ForegroundColor Green
Write-Host "  LLM_trader SPCX: http://localhost:8004   log: logs\llm-trader-spcx.log"
Write-Host "  LLM-TradeBot   : http://localhost:8001   log: logs\llm-tradebot.log  (auto-starts trading)"
Write-Host "  Aggregator     : http://localhost:8500   log: logs\aggregator.log"
Write-Host "  Check health   : .\status.ps1   |   Stop: .\stop-all.ps1" -ForegroundColor Yellow
