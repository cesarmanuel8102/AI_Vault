# install_autostart_task.ps1 — Register Brain V9 auto-start scheduled task
# Run this ONCE. It creates a task that starts Brain V9 + watchdog on every logon.

$taskName = "AI_VAULT_BrainV9_AutoStart"
$scriptPath = "C:\AI_VAULT\tmp_agent\autostart_brain_v9.ps1"

# Remove existing task if any
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Create action: run PowerShell hidden with our watchdog script
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Trigger: at logon with 30 second delay
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT30S"

# Settings: allow on battery, don't stop on battery, restart on failure
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -RestartCount 3 `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

# Register the task
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Auto-start Brain V9 with watchdog on user logon" `
    -RunLevel Highest

# Verify
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "[OK] Task '$taskName' registered successfully" -ForegroundColor Green
    Write-Host "  State:   $($task.State)"
    Write-Host "  Trigger: AtLogOn + 30s delay"
    Write-Host "  Action:  powershell -File $scriptPath (hidden)"
    Write-Host "  Battery: Allowed (won't stop on battery)"
    Write-Host "  Restart: Every 5 min, up to 3 times on failure"
    Write-Host "  Timeout: 365 days (effectively infinite)"
} else {
    Write-Host "[ERROR] Task registration failed" -ForegroundColor Red
}
