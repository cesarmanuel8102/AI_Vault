#Requires -Version 5.1
<#
.SYNOPSIS
    One-command local launcher for Brain Chat V9 + Dashboard.

.DESCRIPTION
    Starts Brain main app on http://127.0.0.1:8091 and Dashboard app on
    http://127.0.0.1:8092 with a deterministic local operator token.
    The token is set only in process environment and printed to console.

.EXAMPLE
    .\tmp_agent\brain_v9\start_local_browser_operational.ps1
#>
$ErrorActionPreference = "Stop"

$LocalToken = "AGENTV2_TEST_ADMIN_TOKEN_08F8_R1B"
$BrainPort = 8091
$DashboardPort = 8092
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $BaseDir "..\..\..")).Path

function Test-PortInUse($Port) {
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        return $false
    } catch {
        return $true
    } finally {
        if ($listener -ne $null) { $listener.Stop() }
    }
}

function Wait-ForHttp($Url, $TimeoutSeconds = 30) {
    $end = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $end) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Write-Host "=" * 64
Write-Host " Brain Chat V9 - Local Browser Operational Launcher"
Write-Host "=" * 64

if (Test-PortInUse $BrainPort) {
    Write-Host "[ERROR] Port $BrainPort is already in use. Stop the existing Brain server first." -ForegroundColor Red
    exit 1
}
if (Test-PortInUse $DashboardPort) {
    Write-Host "[ERROR] Port $DashboardPort is already in use. Stop the existing dashboard server first." -ForegroundColor Red
    exit 1
}

$env:BRAIN_ADMIN_TOKEN = $LocalToken
$env:BRAIN_SAFE_MODE = "false"
$env:BRAIN_START_AUTONOMY = "false"
$env:BRAIN_START_PROACTIVE = "false"
$env:BRAIN_START_SELF_DIAGNOSTIC = "false"
$env:BRAIN_START_QC_LIVE_MONITOR = "false"
$env:BRAIN_WARMUP_MODEL = "false"
$env:BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS = "false"
$env:BRAIN_LOG_LEVEL = "info"

$brainCmd = "python `"$BaseDir\start_safe_server.py`""
$dashboardCmd = "python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port $DashboardPort --log-level info"

Write-Host "[launcher] Starting Brain on port $BrainPort..."
$brainProc = Start-Process -FilePath powershell -ArgumentList "-NoProfile -Command $brainCmd" -WorkingDirectory $RootDir -WindowStyle Hidden -PassThru
Write-Host "[launcher] Starting Dashboard on port $DashboardPort..."
$dashboardProc = Start-Process -FilePath powershell -ArgumentList "-NoProfile -Command $dashboardCmd" -WorkingDirectory $RootDir -WindowStyle Hidden -PassThru

Write-Host "[launcher] Waiting for services to become healthy..."
$brainOk = Wait-ForHttp "http://127.0.0.1:$BrainPort/health" -TimeoutSeconds 60
$dashboardOk = Wait-ForHttp "http://127.0.0.1:$DashboardPort/health" -TimeoutSeconds 30

Write-Host ""
if ($brainOk -and $dashboardOk) {
    Write-Host "Brain and Dashboard are operational" -ForegroundColor Green
    Write-Host ""
    Write-Host "Brain Chat URL: http://127.0.0.1:$BrainPort/ui/"
    Write-Host "Dashboard URL:  http://127.0.0.1:$DashboardPort/"
    Write-Host "Local operator token: $LocalToken"
    Write-Host ""
    Write-Host "Paste the token into the 'Token de operador' field in the UI."
    Write-Host ""
    Write-Host "Health Brain:     http://127.0.0.1:$BrainPort/health"
    Write-Host "Health Dashboard: http://127.0.0.1:$DashboardPort/health"
    Write-Host "Agent status:     http://127.0.0.1:$BrainPort/v2/agent/status"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop both services."
} else {
    Write-Host "Startup incomplete:" -ForegroundColor Red
    Write-Host "   Brain healthy:     $brainOk"
    Write-Host "   Dashboard healthy: $dashboardOk"
    Stop-Process -Id $brainProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $dashboardProc.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

try {
    while ($true) {
        Start-Sleep -Seconds 1
        if ($brainProc.HasExited -or $dashboardProc.HasExited) {
            Write-Host "[launcher] A service exited unexpectedly." -ForegroundColor Red
            break
        }
    }
} finally {
    Write-Host "[launcher] Stopping services..."
    Stop-Process -Id $brainProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $dashboardProc.Id -Force -ErrorAction SilentlyContinue
}
