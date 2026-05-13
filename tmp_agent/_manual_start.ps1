$env:BRAIN_START_AUTONOMY = 'true'
$env:BRAIN_START_PROACTIVE = 'true'
$env:BRAIN_START_SELF_DIAGNOSTIC = 'true'
$env:BRAIN_START_QC_LIVE_MONITOR = 'true'
$env:BRAIN_WARMUP_MODEL = 'true'
$env:SELF_DEV_ENABLED = '1'
$env:SELF_DEV_REQUIRE_APPROVAL = '0'
$env:SELF_DEV_MAX_RISK = '0.4'
$env:GOD_MODE = 'true'
$env:BRAIN_SAFE_MODE = 'false'
$env:BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS = 'true'

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$stderrLog = "C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_$ts.log"
$stdoutLog = "C:/AI_VAULT/tmp_agent/logs/brain_v9_stdout_$ts.log"

$proc = Start-Process python `
    -ArgumentList '-m','brain_v9.main' `
    -WorkingDirectory 'C:/AI_VAULT/tmp_agent' `
    -RedirectStandardError $stderrLog `
    -RedirectStandardOutput $stdoutLog `
    -WindowStyle Hidden -PassThru
Write-Host "Launched PID $($proc.Id), log=$stderrLog"

Start-Sleep -Seconds 35
try {
    $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/health' -TimeoutSec 5
    Write-Host "OK status=$($h.status) safe_mode=$($h.safe_mode)"
} catch {
    Write-Host "FAIL: $($_.Exception.Message)"
    Write-Host "Last 20 lines of stderr:"
    Get-Content $stderrLog -Tail 20
}
