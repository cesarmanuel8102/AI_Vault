$log = 'C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_20260503_210649.log'

Write-Host "=== Proactive scheduler config (7 tasks) ==="
Select-String -Path $log -Pattern 'ProactiveScheduler.*task|Scheduled task|next_run|task_id|Loaded scheduler' |
    Select-Object -First 30 | ForEach-Object { Write-Host "L$($_.LineNumber): $($_.Line)" }

Write-Host "`n=== AutoDebugger 96 errors detail ==="
Select-String -Path $log -Pattern 'AutoDebugger|auto_debug|autodebug' |
    Select-Object -First 25 | ForEach-Object { Write-Host "L$($_.LineNumber): $($_.Line)" }

Write-Host "`n=== Roadmap / pending items mentioned ==="
Select-String -Path $log -Pattern 'roadmap|pending|TODO|next_action|backlog|hypothesis' |
    Select-Object -First 25 | ForEach-Object { Write-Host "L$($_.LineNumber): $($_.Line)" }

Write-Host "`n=== Surgeon / self-healing pending ==="
Select-String -Path $log -Pattern 'Surgeon|self_heal|auto_fix|broken|missing' |
    Select-Object -First 20 | ForEach-Object { Write-Host "L$($_.LineNumber): $($_.Line)" }

Write-Host "`n=== Last 30 log lines ==="
Get-Content $log -Tail 30
