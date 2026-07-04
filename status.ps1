# status.ps1 — quick health check of the confluence stack
$checks = @(
    @{ Name = "orderflow DB   "; Port = 5455 },
    @{ Name = "orderflow OKX  "; Port = 3000 },
    @{ Name = "LLM_trader BTC "; Port = 8000 },
    @{ Name = "LLM-TradeBot   "; Port = 8001 },
    @{ Name = "Aggregator     "; Port = 8500 }
)
foreach ($c in $checks) {
    $listening = Get-NetTCPConnection -LocalPort $c.Port -State Listen -ErrorAction SilentlyContinue
    if ($listening) {
        $owningPid = ($listening | Select-Object -First 1).OwningProcess
        Write-Host ("  UP    {0} :{1}  (pid {2})" -f $c.Name, $c.Port, $owningPid) -ForegroundColor Green
    } else {
        Write-Host ("  DOWN  {0} :{1}" -f $c.Name, $c.Port) -ForegroundColor Red
    }
}
$reaper = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '-File .*reap-browsers\.ps1' }
if ($reaper) { Write-Host "  UP    Chromium reaper    (pid $(($reaper | Select-Object -First 1).ProcessId))" -ForegroundColor Green }
else { Write-Host "  DOWN  Chromium reaper" -ForegroundColor Yellow }

try {
    $state = Invoke-RestMethod -Uri "http://localhost:8500/api/state" -TimeoutSec 4
    Write-Host ""
    foreach ($v in $state.votes) { Write-Host ("  {0,-13} {1,-8} {2}" -f $v.source, $v.direction, $v.detail.Substring(0, [Math]::Min(70, $v.detail.Length))) }
    if ($state.judge) { Write-Host ("  JUDGE: {0} conviction={1}" -f $state.judge.direction, $state.judge.conviction) -ForegroundColor Cyan }
} catch { Write-Host "  (aggregator state unavailable)" -ForegroundColor Yellow }
