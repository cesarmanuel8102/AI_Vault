$r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST `
  -Body (@{ message = "test"; session_id = "diag1" } | ConvertTo-Json) `
  -ContentType "application/json" -TimeoutSec 30
$r | ConvertTo-Json -Depth 5

Write-Host "`n--- Brain process info ---"
Get-Process python | Where-Object { $_.Id -ne $PID } | Select-Object Id, StartTime, CPU | Format-Table

Write-Host "`n--- Latest stderr log ---"
$log = Get-ChildItem "C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "Log: $($log.Name)  Modified: $($log.LastWriteTime)"
Write-Host "--- last 20 lines ---"
Get-Content $log.FullName -Tail 20
