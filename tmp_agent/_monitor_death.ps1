# Live monitor brain — every 5s for up to 5min, capture death moment
$pid_target = 77232
$log = "C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_20260504_143919.log"
$start = Get-Date
$deathReported = $false
$prevLogSize = 0
$prevHealthy = $true
$healthFails = 0

Write-Host "Monitoring PID=$pid_target log=$log"
Write-Host "Time     | Healthy | ProcAlive | LogSize | LastLine"
Write-Host "---------+---------+-----------+---------+----------"

for ($i = 0; $i -lt 60; $i++) {
  $now = Get-Date
  $elapsed = ($now - $start).TotalSeconds
  $proc = Get-Process -Id $pid_target -ErrorAction SilentlyContinue
  $alive = ($null -ne $proc)
  try {
    $r = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 3 -ErrorAction Stop
    $healthy = ($r.status -eq 'healthy')
  } catch {
    $healthy = $false
  }
  $size = (Get-Item $log -ErrorAction SilentlyContinue).Length
  $lastLine = (Get-Content $log -Tail 1 -ErrorAction SilentlyContinue) -replace '\s+', ' '
  if ($lastLine.Length -gt 70) { $lastLine = $lastLine.Substring(0,70) }
  $delta = $size - $prevLogSize
  Write-Host ("{0,7:N0}s | {1,-7} | {2,-9} | {3,5}+{4,-3} | {5}" -f $elapsed, $healthy, $alive, $size, $delta, $lastLine)
  $prevLogSize = $size

  if (-not $alive -and -not $deathReported) {
    Write-Host ""
    Write-Host "=== PROCESS DIED at elapsed=$elapsed s ==="
    Write-Host "--- Last 15 lines of brain log ---"
    Get-Content $log -Tail 15
    Write-Host ""
    $deathReported = $true
    break
  }
  Start-Sleep -Seconds 5
}

if (-not $deathReported) {
  Write-Host ""
  Write-Host "Brain survived ${i} cycles ($($i*5) seconds total). Inconclusive."
}
