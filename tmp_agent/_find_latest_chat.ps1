Write-Host "=== Last 15 events from event_log.jsonl ==="
Get-Content C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl -Tail 15

Write-Host ""
Write-Host "=== Last 10 decision.completed (user tasks) ==="
Get-Content C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl |
  Where-Object { $_ -match 'decision.completed' } |
  Select-Object -Last 10
