$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force (Join-Path $root "tmp_agent/control") | Out-Null
Set-Content -Path (Join-Path $root "tmp_agent/control/STOP_AUTONOMY") -Value "stopped" -Encoding UTF8
Write-Output "Brain autonomy stopped."
