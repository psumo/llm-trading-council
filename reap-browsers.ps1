# =====================================================
# reap-browsers.ps1 — continuous Chromium reaper
# =====================================================
# The llm_trader bot renders charts via Plotly + kaleido 1.x, which drives a
# headless Chromium per render. A slow render trips chart_generator's 30s
# timeout wrapper, abandoning its daemon thread and ORPHANING that Chromium;
# even clean renders linger. Left alone they accumulate (~15-22 procs each,
# GBs of RAM).
#
# A chart render completes in well under a minute and cycles are 5 min apart,
# so any kaleido/choreographer/playwright Chromium ROOT older than the
# threshold is finished work and safe to kill. We never touch a root younger
# than the threshold, so an in-flight render is never interrupted.
#
# Runs detached from start-all.ps1; loops for the life of the stack.
# =====================================================
$ErrorActionPreference = "Continue"
$StaleSeconds = 150     # a render takes <30s; 150s is comfortably past any active one
$IntervalSeconds = 90

while ($true) {
    try {
        $now = Get-Date
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ExecutablePath -match 'ms-playwright|kaleido|choreographer' }
        foreach ($p in $procs) {
            $par = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $p.ParentProcessId) -ErrorAction SilentlyContinue
            $isRoot = (-not $par) -or ($par.Name -ne 'chrome.exe')
            if (-not $isRoot) { continue }
            $age = ($now - $p.CreationDate).TotalSeconds
            if ($age -gt $StaleSeconds) {
                Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                    Where-Object { $_.ProcessId -eq $p.ProcessId -or $_.ParentProcessId -eq $p.ProcessId } |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            }
        }
    } catch { }
    Start-Sleep -Seconds $IntervalSeconds
}
