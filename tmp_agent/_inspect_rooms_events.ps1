$cutoff = (Get-Date).AddHours(-12)
Write-Host "=== Recent files in state/rooms ==="
Get-ChildItem C:/AI_VAULT/tmp_agent/state/rooms -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -gt $cutoff } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 25 LastWriteTime, FullName |
  Format-Table -AutoSize -Wrap

Write-Host ""
Write-Host "=== Recent decision.completed in event log (filter scheduler out) ==="
Get-Content C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl -Tail 200 |
  Where-Object { $_ -match 'decision.completed' -or $_ -match 'capability.failed' -or $_ -match 'chat' } |
  Select-Object -Last 30
