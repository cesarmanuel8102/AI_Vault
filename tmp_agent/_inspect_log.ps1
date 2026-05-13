$latest = Get-ChildItem C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "=== $($latest.Name) ==="
Select-String -Path $latest.FullName -Pattern 'Anthropic|kimi|sonnet4|TIMEOUT|wall_clock|model_key|r31_ui_v2' | Select-Object -Last 40 | ForEach-Object { Write-Host $_.Line }
