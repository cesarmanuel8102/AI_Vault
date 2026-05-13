$logs = Get-ChildItem C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 3
foreach ($l in $logs) {
    Write-Host "=== $($l.Name) ($($l.LastWriteTime)) ==="
    Get-Content $l.FullName -Tail 25
}
