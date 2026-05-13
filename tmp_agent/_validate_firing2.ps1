Write-Host "=== Killing brain ==="
$pids = (Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) | Where-Object { $_ -ne 0 }
foreach ($p in $pids) { try { Stop-Process -Id $p -Force; Write-Host "Killed PID $p" } catch {} }

for ($i=0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8090/health" -TimeoutSec 3
    if ($h.status -eq "healthy") { Write-Host "Brain healthy after $($i*2)s"; break }
  } catch {}
}

# Use SAME session_id, send 5+ msgs including a "sigue" within 90s
$sid = "r4_cold_start_validator"
$queries = @("sigue", "continua", "mas", "hola", "1+1", "extra forzar persist")
foreach ($q in $queries) {
  $body = @{ message = $q; session_id = $sid } | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST `
      -Body $body -ContentType "application/json" -TimeoutSec 60
    $resp = $r.response
    if ($resp.Length -gt 80) { $resp = $resp.Substring(0,80) + "..." }
    Write-Host "[$q] -> $resp"
  } catch { Write-Host "[$q] FAIL: $_" }
}

Write-Host "`n=== Final metrics ==="
Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json"
