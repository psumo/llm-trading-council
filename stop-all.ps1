# =====================================================
# stop-all.ps1 — best-effort teardown of the confluence stack
# =====================================================
# Stops, by port and by window title:
#   * aggregator (8500), LLM_trader (8000), LLM-TradeBot (8001)
#   * orderflow node service
#   * orderflow TimescaleDB container (keeps data)
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
# =====================================================
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot

function Stop-ByPort($port, $label) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { Write-Host "  $label (:$port) not listening" -ForegroundColor DarkGray; return }
    foreach ($procId in ($conns.OwningProcess | Select-Object -Unique)) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "  stopped $label (:$port) pid=$procId" -ForegroundColor Green
        } catch {
            Write-Host "  could not stop pid=$procId for $label : $_" -ForegroundColor Yellow
        }
    }
}

function Stop-ByWindowTitle($title) {
    Get-Process | Where-Object { $_.MainWindowTitle -eq $title } | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop;
              Write-Host "  stopped window '$title' pid=$($_.Id)" -ForegroundColor Green }
        catch { Write-Host "  could not stop window '$title': $_" -ForegroundColor Yellow }
    }
}

Write-Host "=== Stopping confluence stack ===" -ForegroundColor Cyan

# Stop the dashboards by port.
Stop-ByPort 8500 "aggregator"
Stop-ByPort 8001 "llm-tradebot"
Stop-ByPort 8000 "llm-trader"
Stop-ByPort 8002 "llm-trader-eth"
Stop-ByPort 8003 "llm-trader-sol"
Stop-ByPort 8004 "llm-trader-spcx"

# Stop the orderflow node collector: port 3000 (detached) or window title (legacy).
Stop-ByPort 3000 "orderflow-okx"
Stop-ByWindowTitle "orderflow-node"

# Catch stray bot processes (detached/hidden launches have no window).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "*trading-confluence*" } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
              Write-Host "  stopped stray python pid=$($_.ProcessId)" -ForegroundColor Green }
        catch { }
    }

# Catch any launcher windows left over (legacy window-based launches).
foreach ($t in @("confluence-aggregator","llm-trader","llm-tradebot")) {
    Stop-ByWindowTitle $t
}

# Stop the DB container (keeps the named volume / data).
Write-Host "Stopping orderflow DB container..." -ForegroundColor Cyan
$compose = Join-Path $root "orderflow\docker-compose.db.yml"
docker compose -f $compose stop 2>$null
if ($LASTEXITCODE -ne 0) {
    docker stop confluence_orderflow_db 2>$null | Out-Null
}

# Stop the continuous Chromium reaper loop.
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '-File .*reap-browsers\.ps1' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# llm-trader renders charts via Playwright Chromium; force-killed instances
# orphan their browser trees. Sweep them so they never accumulate.
$pw = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -match 'ms-playwright' -or $_.CommandLine -match 'playwright.driver' }
if ($pw) {
    Write-Host ("Sweeping " + @($pw).Count + " orphaned Playwright browser processes...") -ForegroundColor Cyan
    $pw | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

Write-Host "=== Teardown complete ===" -ForegroundColor Green
