#Requires -RunAsAdministrator
param(
    [string]$Root = "C:\AI_VAULT_CANONICAL",
    [int]$Port = 8091
)

$ErrorActionPreference = "Stop"
$logDir = "$Root\tmp_agent\runtime"
$null = New-Item -ItemType Directory -Force -Path $logDir

function Write-Log {
    param([string]$msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $msg"
    Write-Host $line
    Add-Content -Path "$logDir\brain_8091_restart.log" -Value $line
}

Write-Log "=== Brain 8091 Agent V2 Restart ==="
Write-Log "Root: $Root"
Write-Log "Port: $Port"

# Find and kill existing processes on port
$listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
foreach ($conn in $listeners) {
    try {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction Stop
        Write-Log "Killing process $($proc.Id) - $($proc.ProcessName) on port $Port"
        Stop-Process -Id $conn.OwningProcess -Force
    } catch {
        Write-Log "WARNING: Could not kill PID $($conn.OwningProcess): $_"
    }
}

Start-Sleep -Seconds 2

# Start Brain 8091
Set-Location $Root
$env:PYTHONPATH = "$Root;$env:PYTHONPATH"
Write-Log "Starting Brain 8091 from $Root"

$proc = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "tmp_agent.brain_v9.main:app", "--host", "127.0.0.1", "--port", $Port `
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

# Verify Agent V2
for ($i = 0; $i -lt 5; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v2/agent/status" -Method GET -TimeoutSec 5
        Write-Log "Agent V2 Status: $($resp | ConvertTo-Json -Compress)"
        if ($resp.canonical_for_new_agent_runs -eq $true) {
            Write-Log "SUCCESS: Agent V2 is canonical"
        }
        break
    } catch {
        Write-Log "Agent V2 check attempt $($i+1)/5 failed: $_"
        Start-Sleep -Seconds 1
    }
}

Write-Log "=== Restart Complete ==="
