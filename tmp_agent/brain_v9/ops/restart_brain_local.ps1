# restart_brain_local.ps1
# Restart Brain V9 local services: stop (port-owner PID only) then start, then verify health.
# Front: FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01
#
# Safety:
# - Delegates stopping to stop_brain_local.ps1 (kills ONLY port-owner PIDs, never all python.exe).
# - Delegates starting to start_brain_local.ps1 (canonical safe launcher, token from env).
# - Token never printed in full. No memory/FAISS/broker/trading/source/git touched.

[CmdletBinding()]
param(
    [switch]$BrainOnly,
    [switch]$DashboardOnly,
    [switch]$Force   # passed through to stop (skip confirm) and start (no-op safety)
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$stop = Join-Path $scriptDir "stop_brain_local.ps1"
$start = Join-Path $scriptDir "start_brain_local.ps1"
$status = Join-Path $scriptDir "status_brain_local.ps1"

"=== restart_brain_local: STOP ==="
$stopArgs = @($stop)
if ($BrainOnly)   { $stopArgs += "-BrainOnly" }
if ($DashboardOnly) { $stopArgs += "-DashboardOnly" }
if ($Force)       { $stopArgs += "-Force" }
& powershell -NoProfile -ExecutionPolicy Bypass -File $stopArgs

Start-Sleep -Seconds 2

"=== restart_brain_local: START ==="
$startArgs = @($start)
if ($BrainOnly)   { $startArgs += "-BrainOnly" }
if ($DashboardOnly) { $startArgs += "-DashboardOnly" }
& powershell -NoProfile -ExecutionPolicy Bypass -File $startArgs

Start-Sleep -Seconds 4

"=== restart_brain_local: VERIFY ==="
& powershell -NoProfile -ExecutionPolicy Bypass -File $status
