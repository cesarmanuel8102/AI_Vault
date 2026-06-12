param([switch]$Enable)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
  $env:PYTHONPATH = "$root;$root\tmp_agent"
  python -m tmp_agent.brain_v9.autonomy.autonomy_scheduler | Out-Null
  $taskName = "BrainGovernedAutonomy"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$root\tools\brain_autonomy_run_once.ps1`""
  $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(60) -RepetitionInterval (New-TimeSpan -Minutes 60)
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Governed Brain autonomy run_once task" -Force | Out-Null
  if (-not $Enable) { Disable-ScheduledTask -TaskName $taskName | Out-Null }
  Write-Output "Scheduled task created. Enabled=$($Enable.IsPresent)"
} finally { Pop-Location }
