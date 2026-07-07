$ErrorActionPreference = "SilentlyContinue"

$reportDir = "C:\AI_VAULT_CANONICAL\tmp_agent\front_brain_agent_v2_identity_guard_and_intent_floor_widen_02"
$pidFile = Join-Path $reportDir "brain_server.pid"

if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile | Select-Object -First 1).Trim()
    Write-Output "Killing old PID $oldPid..."
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Also kill anything still binding 8091
$conn = Get-NetTCPConnection -LocalPort 8091 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    foreach ($c in $conn) {
        Write-Output "Killing residual listener PID $($c.OwningProcess)..."
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

$env:BRAIN_ADMIN_TOKEN = $env:BRAIN_ADMIN_TOKEN
if (-not $env:BRAIN_ADMIN_TOKEN -or $env:BRAIN_ADMIN_TOKEN.Trim() -eq "") {
    Write-Error "BRAIN_ADMIN_TOKEN is required. Set it in your environment."
    exit 2
}

$stdoutLog = Join-Path $reportDir "brain_server_stdout.log"
$stderrLog = Join-Path $reportDir "brain_server_stderr.log"

if (Test-Path $stdoutLog) { Move-Item -Force $stdoutLog "$stdoutLog.prev" -ErrorAction SilentlyContinue }
if (Test-Path $stderrLog) { Move-Item -Force $stderrLog "$stderrLog.prev" -ErrorAction SilentlyContinue }

$launcher = "C:\AI_VAULT_CANONICAL\tmp_agent\brain_v9\start_safe_server.py"
$workDir  = "C:\AI_VAULT_CANONICAL"

$proc = Start-Process -FilePath "python" `
    -ArgumentList $launcher `
    -WorkingDirectory $workDir `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $pidFile -Value $proc.Id
Write-Output "RESTARTED_PID=$($proc.Id)"
