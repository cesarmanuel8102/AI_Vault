$log = Get-ChildItem 'C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "Log: $($log.FullName)"
Write-Host "`n=== Last 60 lines mentioning r98 / read_file / tool ==="
Get-Content $log.FullName -Tail 200 | Select-String -Pattern 'r98|read_file|FileNotFound|tool_call|chat_excellence|agent_orav done|HTTP-500|raised|ERROR|WARNING' -SimpleMatch | Select-Object -Last 60 | ForEach-Object { $_.Line }
