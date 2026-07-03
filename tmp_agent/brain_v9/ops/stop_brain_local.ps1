# stop_brain_local.ps1
# Safely stop Brain V9 local services by killing ONLY the PID that owns the target port.
# Front: FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01
#
# Safety:
# - NEVER kills all python.exe. Resolves the owning PID of the specific port and stops only that.
# - Shows the process command line BEFORE stopping.
# - Confirms before stopping unless -Force.
# - Token (if present) is never printed in full.
# - Does NOT touch memory/FAISS/broker/trading/source files. Does NOT run git.

[CmdletBinding()]
param(
    [switch]$BrainOnly,     # stop only 8091
    [switch]$DashboardOnly, # stop only 8092
    [switch]$Force          # skip confirmation prompt
)

$ErrorActionPreference = "Continue"

function Redact-Token([string]$t) {
    if ([string]::IsNullOrEmpty($t)) { return "<none>" }
    if ($t.Length -le 8) { return "***" }
    return $t.Substring(0,8) + "***REDACTED"
}

function Stop-PortOwner([int]$port, [string]$label) {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if (-not $conns) {
        "$label (port $port): not listening. Nothing to stop."
        return
    }
    $owner = $conns.OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue
    $cmd = if ($proc) { $proc.CommandLine } else { "<unknown>" }
    if ($cmd.Length -gt 120) { $cmd = $cmd.Substring(0,120) + "..." }
    "$label (port $port): owner PID=$owner"
    "  command: $cmd"
    if (-not $Force) {
        $resp = Read-Host "Stop PID $owner ($label on $port)? [y/N]"
        if ($resp -notmatch '^[yY]') { "Aborted (no action)."; return }
    }
    Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    "Stopped PID $owner ($label on $port)."
}

if ($BrainOnly -and -not $DashboardOnly) {
    Stop-PortOwner -port 8091 -label "Brain API"
} elseif ($DashboardOnly -and -not $BrainOnly) {
    Stop-PortOwner -port 8092 -label "Dashboard"
} else {
    Stop-PortOwner -port 8091 -label "Brain API"
    Stop-PortOwner -port 8092 -label "Dashboard"
}

"Token: " + (Redact-Token $env:BRAIN_ADMIN_TOKEN)
"stop_brain_local complete."
