$log = Get-ChildItem 'C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "Log: $($log.FullName) ($('{0:N1}' -f ($log.Length/1KB)) KB)" -ForegroundColor Cyan
Write-Host "--- ProactiveScheduler/chat_excellence (last 80) ---" -ForegroundColor Yellow
Select-String -Path $log.FullName -Pattern "ProactiveScheduler|chat_excellence|ChatExcellence|Scheduler" | Select-Object -Last 80 | ForEach-Object { $_.Line }
