$st = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/proactive/status'
Write-Host "running_task: $($st.running_task)"
Write-Host "tasks:"
$st.tasks | Where-Object { $_.id -eq 'chat_excellence' } | ConvertTo-Json -Depth 4
Write-Host "`nrecent_history (last 5):"
$st.recent_history | Select-Object -Last 5 | ConvertTo-Json -Depth 3
