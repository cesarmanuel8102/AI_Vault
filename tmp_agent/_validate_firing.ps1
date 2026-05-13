Write-Host "=== Killing brain to load _persist fix ==="
$pids = (Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($p in $pids) {
  try { Stop-Process -Id $p -Force; Write-Host "Killed PID $p" } catch {}
}

Write-Host "`n=== Waiting for watchdog respawn ==="
$ok = $false
for ($i=0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8090/health" -TimeoutSec 3
    if ($h.status -eq "healthy") { $ok = $true; Write-Host "Brain healthy after $($i*2)s"; break }
  } catch {}
}
if (-not $ok) { Write-Host "Brain did NOT come back"; exit 1 }

Write-Host "`n=== Test cold_start_guard within 90s ==="
$sid = "r4_validator_firing_test"
# Short msg should trigger cold_start_guard validator
$queries = @("hi", "ok", "test", "yo", "ping", "extra")
foreach ($q in $queries) {
  $body = @{ message = $q; session_id = $sid } | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST `
      -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host "[$q] ok=$($r.success)"
  } catch { Write-Host "[$q] FAIL" }
}

Write-Host "`n=== Final metrics ==="
Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json"
