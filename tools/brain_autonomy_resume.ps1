$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Remove-Item -Path (Join-Path $root "tmp_agent/control/PAUSE_AUTONOMY") -ErrorAction SilentlyContinue
Remove-Item -Path (Join-Path $root "tmp_agent/control/STOP_AUTONOMY") -ErrorAction SilentlyContinue
Write-Output "Brain autonomy resumed."
