<#
.SYNOPSIS
    Start Brain V9 Dashboard + Chat Runtime
.DESCRIPTION
    Starts the Brain V9 server on port 8090 with correct Windows paths.
    Waits until /health returns 200 before reporting success.
    Includes stop/restart helpers.
.NOTES
    Requires: Python 3.11+ with uvicorn, fastapi installed
    Port: 8090
    Host: 127.0.0.1
#>
param(
    [switch]$SafeMode,
    [switch]$Stop,
    [switch]$Restart
)

$RepoRoot = "C:\AI_VAULT"
$ServerDir = "$RepoRoot\tmp_agent\brain_v9"
$Port = 8090
$HostAddr = "127.0.0.1"
$HealthUrl = "http://${HostAddr}:${Port}/health"
$LogFile = "$RepoRoot\tmp_agent\runtime_dashboard_chat_recovery_01\server.log"

function Stop-BrainServer {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and ($_.CommandLine -match "brain_v9.main:app|main:app.*8090")
    } | ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId)..."
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

function Wait-ForHealth {
    param([int]$TimeoutSec = 30)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try {
            $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                return $true
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if ($Stop) {
    Stop-BrainServer
    Write-Host "Brain V9 stopped."
    exit 0
}

if ($Restart) {
    Stop-BrainServer
}

# Check if already running
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.CommandLine -match "brain_v9.main:app|main:app.*8090")
}
if ($existing) {
    Write-Host "Brain V9 already running (PID $($existing.ProcessId))."
    if (-not (Wait-ForHealth -TimeoutSec 5)) {
        Write-Warning "Health check failed; restarting..."
        Stop-BrainServer
    } else {
        Write-Host "Health check OK."
        exit 0
    }
}

$Env:BRAIN_HOST = $HostAddr
$Env:BRAIN_PORT = "$Port"

$Cmd = "python"
$Args = @("-m", "uvicorn", "brain_v9.main:app", "--host", $HostAddr, "--port", "$Port", "--log-level", "info")

if ($SafeMode) {
    $Env:BRAIN_SAFE_MODE = "true"
    $Env:BRAIN_START_AUTONOMY = "false"
    $Args = @("start_safe_server.py")
} else {
    $Args = @("start_full_server.py")
}

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

$proc = Start-Process -FilePath $Cmd -ArgumentList $Args `
    -WorkingDirectory $ServerDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError "$LogFile.err" `
    -PassThru

Write-Host "Started Brain V9 (PID $($proc.Id)). Waiting for health..."

if (Wait-ForHealth -TimeoutSec 60) {
    Write-Host "SUCCESS: Brain V9 is alive on http://${HostAddr}:${Port}"
    Write-Host "Dashboard: http://${HostAddr}:${Port}/dashboard"
    Write-Host "Chat API: POST http://${HostAddr}:${Port}/chat"
    Write-Host "Health:  http://${HostAddr}:${Port}/health"
    Write-Host "Docs:    http://${HostAddr}:${Port}/docs"
} else {
    Write-Error "FAILED: Health check did not pass within 60s."
    Write-Error "Check logs: $LogFile"
    exit 1
}
