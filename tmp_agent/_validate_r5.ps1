Write-Host "=== Killing brain to load R5 changes ==="
$pids = (Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) | Where-Object { $_ -ne 0 }
foreach ($p in $pids) { try { Stop-Process -Id $p -Force; Write-Host "Killed PID $p" } catch {} }

for ($i=0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8090/health" -TimeoutSec 3
    if ($h.status -eq "healthy") { Write-Host "Brain healthy after $($i*2)s"; break }
  } catch {}
}

Write-Host "`n=== R5.3 test: correction ack should NOT route to agent ==="
$sid = "r5_correction_ack_test"
$body1 = @{ message = "que es 2+2"; session_id = $sid } | ConvertTo-Json -Compress
$r1 = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST -Body $body1 -ContentType "application/json" -TimeoutSec 60
Write-Host "Turn1 [2+2]: model=$($r1.model_used) resp=$($r1.response.Substring(0, [Math]::Min(60, $r1.response.Length)))"

$body2 = @{ message = "no, eso es incorrecto, el resultado real es 5"; session_id = $sid } | ConvertTo-Json -Compress
$r2 = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST -Body $body2 -ContentType "application/json" -TimeoutSec 60
Write-Host "Turn2 [correction]: model=$($r2.model_used) resp=$($r2.response.Substring(0, [Math]::Min(120, $r2.response.Length)))"

$expected = "Anotado"
if ($r2.response -match $expected) {
  Write-Host "`nR5.3 PASS: explicit ack returned"
} else {
  Write-Host "`nR5.3 FAIL: expected ack containing '$expected'"
}

Write-Host "`n=== R5.1 test: cross-session metrics share singleton ==="
# Send 5 msgs across 5 different session_ids, persist threshold should fire on 5th
$start_total = (Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json" | ConvertFrom-Json).total_conversations
Write-Host "total_conversations BEFORE: $start_total"

for ($i=1; $i -le 5; $i++) {
  $body = @{ message = "msg $i"; session_id = "r5_singleton_test_$i" } | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host "[r5_singleton_test_$i] model=$($r.model_used)"
  } catch { Write-Host "[i=$i] FAIL" }
}

Start-Sleep -Seconds 2
$end_total = (Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json" | ConvertFrom-Json).total_conversations
Write-Host "total_conversations AFTER: $end_total"

# Pre-R5: each new session would load 1755 from disk and never increment beyond
# 1756. With singleton, total should grow by ~7 (2 from R5.3 + 5 from singleton test).
$delta = $end_total - $start_total
Write-Host "Delta: $delta (expected >= 5)"
if ($delta -ge 5) {
  Write-Host "R5.1 PASS: singleton shares state across sessions"
} else {
  Write-Host "R5.1 FAIL: delta too small, sessions not sharing metrics"
}

Write-Host "`n=== Final metrics file ==="
Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json"
