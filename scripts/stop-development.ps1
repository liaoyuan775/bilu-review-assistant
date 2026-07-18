$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $root ".runtime\bilu-development.json"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

function Stop-ProcessTree([int]$ProcessId) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) { Stop-ProcessTree $child.ProcessId }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$ports = @(4178, 8790)
$rootPid = $null
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
    if ($state.workspace -eq $root) {
        $rootPid = [int]$state.rootPid
        $ports = @([int]$state.frontendPort, [int]$state.backendPort)
    }
}

if ($rootPid) { Stop-ProcessTree $rootPid }
foreach ($port in $ports) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) { Stop-ProcessTree $listener.OwningProcess }
}

Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
$remaining = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $ports }
if ($remaining) {
    $remaining | Format-Table LocalPort, OwningProcess
    throw "Some development processes are still listening."
}
Write-Host "Bilu development environment stopped." -ForegroundColor Green
