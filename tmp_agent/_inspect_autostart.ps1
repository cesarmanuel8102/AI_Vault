# Cleanup leftover gate task
schtasks.exe /Delete /TN BrainHealthGate_ce_prop_20260504_133441 /F 2>&1 | Out-Host

# Inspect autostart task action
$t = Get-ScheduledTask -TaskName AI_VAULT_BrainV9_AutoStart
Write-Host "--- Autostart task ---"
$t.Actions | Format-List
$info = Get-ScheduledTaskInfo -TaskName AI_VAULT_BrainV9_AutoStart
Write-Host "LastRunTime  : $($info.LastRunTime)"
Write-Host "LastResult   : $($info.LastTaskResult)"
Write-Host "NextRun      : $($info.NextRunTime)"
