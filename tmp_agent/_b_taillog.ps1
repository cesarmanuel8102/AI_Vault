$log = Get-ChildItem C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ("LOG: {0}" -f $log.FullName)
Write-Host "--- last 100 lines ---"
Get-Content $log.FullName -Tail 100
Write-Host ""
Write-Host "--- grep abstract|FailureLearner|llm.query ---"
Get-Content $log.FullName | Select-String -Pattern "abstract|FailureLearner|llm.query|model_priority" | Select-Object -Last 30
