Get-ChildItem 'C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 8 |
  Format-Table Name, LastWriteTime, @{N='KB';E={[math]::Round($_.Length/1KB,1)}} -AutoSize

Write-Host "`n=== Memory state files ==="
Get-ChildItem 'C:/AI_VAULT/tmp_agent/state/memory' -Recurse -Filter 'short_term.json' -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 |
  Format-Table FullName, LastWriteTime, @{N='KB';E={[math]::Round($_.Length/1KB,1)}} -AutoSize
