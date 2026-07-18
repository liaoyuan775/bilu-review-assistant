$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $root ".runtime"
$stateFile = Join-Path $runtimeDir "bilu-development.json"
$frontendPort = 4178
$backendPort = 8790

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$Host.UI.RawUI.WindowTitle = "Bilu Review Assistant - Development Logs"

function Get-PortOwner([int]$Port) {
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess
}

foreach ($port in @($frontendPort, $backendPort)) {
    $owner = Get-PortOwner $port
    if ($owner) {
        $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
        throw "Port $port is already in use by PID $owner ($($process.ProcessName)). Run the shutdown script or stop that process first."
    }
}

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$concurrently = Join-Path $root "node_modules\.bin\concurrently.cmd"
if (-not (Test-Path -LiteralPath $python)) { throw "Backend virtual environment is missing: $python" }
if (-not (Test-Path -LiteralPath $concurrently)) { throw "Dependencies are missing. Run npm install first." }

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
@{
    rootPid = $PID
    frontendPort = $frontendPort
    backendPort = $backendPort
    startedAt = (Get-Date).ToString("o")
    workspace = $root
} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8

$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$env:BILU_DEBUG_LOGS = "true"
$env:BILU_LOG_PAYLOADS = "false"
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$backendPort"

Write-Host ""
Write-Host "Bilu development environment" -ForegroundColor Cyan
Write-Host "Frontend: http://127.0.0.1:$frontendPort" -ForegroundColor Cyan
Write-Host "Backend : http://127.0.0.1:$backendPort" -ForegroundColor Green
Write-Host "API docs: http://127.0.0.1:$backendPort/api/docs" -ForegroundColor Green
Write-Host "Log file: backend\logs\development.log" -ForegroundColor Yellow
Write-Host "Payloads : redacted summaries (set BILU_LOG_PAYLOADS=true only for approved test data)" -ForegroundColor Yellow
Write-Host "Close with the shutdown script or Ctrl+C." -ForegroundColor DarkGray
Write-Host ""

$frontendCommand = "npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port $frontendPort --strictPort"
$backendCommand = "`"$python`" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $backendPort --reload --log-level debug"

try {
    Push-Location $root
    & $concurrently -k --kill-others-on-fail -n FRONTEND,BACKEND -c cyan,green $frontendCommand $backendCommand
}
finally {
    Pop-Location
    Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
}
