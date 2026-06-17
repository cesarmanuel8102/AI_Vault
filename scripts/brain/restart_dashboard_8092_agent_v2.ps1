#Requires -RunAsAdministrator
param(
    [string]$Root = "C:\AI_VAULT_CANONICAL",
    [int]$Port = 8092,
    [switch]$SkipZombieWarning
)

$ErrorActionPreference = "Stop"
$logDir = "$Root\tmp_agent\runtime"
$null = New-Item -ItemType Directory -Force -Path $logDir

function Write-Log {
    param([string]$msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $msg"
    Write-Host $line
    Add-Content -Path "$logDir\dashboard_8092_restart.log" -Value $line
}

Write-Log "=== Dashboard 8092 Agent V2 Restart ==="
Write-Log "Root: $Root"
Write-Log "Port: $Port"

# Zombie detection
$zombie = $false
$listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
foreach ($conn in $listeners) {
    try {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction Stop
        Write-Log "Found process $($proc.Id) - $($proc.ProcessName) on port $Port"
        Stop-Process -Id $conn.OwningProcess -Force
        Write-Log "Killed process $($proc.Id)"
    } catch {
        Write-Log "WARNING: Port $Port has PID $($conn.OwningProcess) but process not found (ZOMBIE). This requires Windows reboot or netsh reset."
        $zombie = $true
        if (-not $SkipZombieWarning) {
            Write-Host "CRITICAL: Zombie socket detected on port $Port." -ForegroundColor Red
            Write-Host "The process died but Windows TCP socket remains in LISTENING state." -ForegroundColor Red
            Write-Host "Solution: Restart Windows, OR run: netsh int ip reset, then reboot." -ForegroundColor Yellow
            Write-Host "Workaround: Use 8091 for Agent V2 status until resolved." -ForegroundColor Yellow
            Read-Host "Press Enter to continue anyway (dashboard may fail to bind)"
        }
    }
}

Start-Sleep -Seconds 2

# Start Dashboard 8092
Set-Location $Root
$env:PYTHONPATH = "$Root;$env:PYTHONPATH"
Write-Log "Starting Dashboard 8092 from $Root"

$proc = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "tmp_agent.brain_v9.dashboard.dashboard_app:app", "--host", "127.0.0.1", "--port", $Port `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

Write-Log "Started PID $($proc.Id)"

# Wait and verify
Start-Sleep -Seconds 5
for ($i = 0; $i -lt 10; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method GET -TimeoutSec 5
        Write-Log "Health OK: $($resp | ConvertTo-Json -Compress)"
        break
    } catch {
        Write-Log "Health check attempt $($i+1)/10 failed: $_"
        Start-Sleep -Seconds 1
    }
}

# Verify Agent V2 route
for ($i = 0; $i -lt 5; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/brain-dashboard/agent-v2/status" -Method GET -TimeoutSec 5
        Write-Log "Agent V2 Dashboard Route OK: $($resp | ConvertTo-Json -Compress)"
        break
    } catch {
        Write-Log "Agent V2 route check attempt $($i+1)/5 failed: $_"
        if ($i -eq 4) {
            Write-Log "WARNING: /brain-dashboard/agent-v2/status not responding. If zombie socket, this is expected."
        }
        Start-Sleep -Seconds 1
    }
}

Write-Log "=== Restart Complete ==="
