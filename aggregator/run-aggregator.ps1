# =====================================================
# Signal-Confluence Aggregator launcher (PowerShell)
# =====================================================
# Activates the dedicated uv venv and starts the aggregator. Dashboard at
# http://localhost:8500. Reads config from .\config.yaml.
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\run-aggregator.ps1
# Stop:   Ctrl+C
# =====================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

. "$PSScriptRoot\.venv\Scripts\Activate.ps1"

Write-Host "Starting Confluence Aggregator (SPCXUSDT)..." -ForegroundColor Cyan
Write-Host "Dashboard: http://localhost:8500" -ForegroundColor Cyan

python main.py
