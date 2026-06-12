$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force (Join-Path $root "tmp_agent/control") | Out-Null
Set-Content -Path (Join-Path $root "tmp_agent/control/PAUSE_AUTONOMY") -Value "paused" -Encoding UTF8
Write-Output "Brain autonomy paused."
