$log = (Get-ChildItem 'C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
Write-Host "Log: $log"
Get-Content $log -Tail 150
