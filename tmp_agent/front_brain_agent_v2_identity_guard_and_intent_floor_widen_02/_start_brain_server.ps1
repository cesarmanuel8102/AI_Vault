$ErrorActionPreference = "Stop"

# Ensure token matches what the benchmark runner uses
if (-not $env:BRAIN_ADMIN_TOKEN -or $env:BRAIN_ADMIN_TOKEN.Trim() -eq "") {
    Write-Error "BRAIN_ADMIN_TOKEN is required. Set it in your environment."
    exit 2
}

$reportDir = "C:\AI_VAULT_CANONICAL\tmp_agent\front_brain_agent_v2_identity_guard_and_intent_floor_widen_02"
$stdoutLog = Join-Path $reportDir "brain_server_stdout.log"
$stderrLog = Join-Path $reportDir "brain_server_stderr.log"
$pidFile = Join-Path $reportDir "brain_server.pid"

# Rotate old logs by moving to .prev
if (Test-Path $stdoutLog) { Move-Item -Force $stdoutLog "$stdoutLog.prev" }
if (Test-Path $stderrLog) { Move-Item -Force $stderrLog "$stderrLog.prev" }

$launcher = "C:\AI_VAULT_CANONICAL\tmp_agent\brain_v9\start_safe_server.py"
$workDir  = "C:\AI_VAULT_CANONICAL"

Write-Output "Launching Brain server with BRAIN_ADMIN_TOKEN set..."
$proc = Start-Process -FilePath "python" `
    -ArgumentList $launcher `
    -WorkingDirectory $workDir `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $pidFile -Value $proc.Id
Write-Output "STARTED_PID=$($proc.Id)"
Write-Output "STDOUT_LOG=$stdoutLog"
Write-Output "STDERR_LOG=$stderrLog"
