# R9.6/R9.7/R9.9 validation
Write-Host "=== R9.6: Ack all alerts ==="
$body = @{ all = $true; actor = 'validation' } | ConvertTo-Json
$ack = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/scheduler/alerts/ack' -Method POST -ContentType 'application/json' -Body $body
$ack | ConvertTo-Json

Write-Host "`n=== R9.6: Verify alerts file (all acknowledged?) ==="
$alerts = Get-Content 'C:\AI_VAULT\tmp_agent\state\scheduler_alerts.json' -Raw | ConvertFrom-Json
$total = $alerts.Count
$acked = ($alerts | Where-Object { $_.acknowledged -eq $true }).Count
Write-Host "total=$total acked=$acked"

Write-Host "`n=== R9.7: Force-run chat_excellence ==="
$run = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/proactive/run/chat_excellence' -Method POST
$run | ConvertTo-Json -Depth 4

Write-Host "`n=== R9.9: CB endpoint ==="
$cb = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/llm/circuit_breaker' -Method GET
$cb | ConvertTo-Json -Depth 5

Write-Host "`n=== R9.7: Bad task_id should 404 ==="
try {
  Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/proactive/run/nonexistent_task' -Method POST -ErrorAction Stop
} catch {
  Write-Host "EXPECTED ERROR: $($_.Exception.Response.StatusCode.value__) $($_.Exception.Message)"
}
