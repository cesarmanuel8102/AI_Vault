$f = Get-ChildItem C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $f.FullName -Tail 120 | Where-Object { $_ -match "WARNING|ERROR|exception|fail|Traceback" -or $_ -match "chat.*session|AgentLoop" }
