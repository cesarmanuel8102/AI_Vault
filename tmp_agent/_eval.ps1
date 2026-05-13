$log = Get-ChildItem C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ("=== Last 100 lines of {0} ===" -f $log.Name) -ForegroundColor Cyan
Get-Content $log.FullName -Tail 100

Write-Host ""
Write-Host "=== Mutations log ===" -ForegroundColor Cyan
$mutLog = "C:/AI_VAULT/tmp_agent/state/mutations/mutation_log.jsonl"
if (Test-Path $mutLog) {
    Get-Content $mutLog -Tail 10
} else {
    Write-Host "(no mutations log yet)"
}

Write-Host ""
Write-Host "=== Learned patterns ===" -ForegroundColor Cyan
Get-ChildItem C:/AI_VAULT/tmp_agent/state/learned_patterns/*.json -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host ("--- {0} ---" -f $_.Name)
    Get-Content $_.FullName | ConvertFrom-Json | ConvertTo-Json -Depth 4
}
