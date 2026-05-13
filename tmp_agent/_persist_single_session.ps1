$sid = "r4_persist_validate_single"
$queries = @("hola", "1+1", "color", "3*3", "dia", "extra para forzar persist")
foreach ($q in $queries) {
  $body = @{ message = $q; session_id = $sid } | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST `
      -Body $body -ContentType "application/json" -TimeoutSec 90
    Write-Host "[$q] -> $($r.model_used) success=$($r.success)"
  } catch {
    Write-Host "[$q] FAIL: $_"
  }
}

Write-Host "`n--- Metrics file after persist trigger ---"
Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json"
