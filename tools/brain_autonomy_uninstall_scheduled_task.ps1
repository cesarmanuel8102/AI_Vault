$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "BrainGovernedAutonomy" -Confirm:$false -ErrorAction SilentlyContinue
Write-Output "Scheduled task removed if present."
