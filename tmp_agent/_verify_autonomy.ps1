$log = 'C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_20260503_210649.log'
Write-Host "=== Searching log for autonomy/proactive/diagnostic markers ==="
Select-String -Path $log -Pattern 'AutonomyManager|ProactiveScheduler|SelfDiagnostic|QC Live|Warmup|\[SAFE\]|\[OK\]' |
    Select-Object -First 40 |
    ForEach-Object { Write-Host "L$($_.LineNumber): $($_.Line)" }

Write-Host "`n=== Env var sanity check (from running brain process) ==="
$brain = Get-CimInstance Win32_Process -Filter "ProcessId=65304"
Write-Host "Brain PID: $($brain.ProcessId), Parent: $($brain.ParentProcessId)"
