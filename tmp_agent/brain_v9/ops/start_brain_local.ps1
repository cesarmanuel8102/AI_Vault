# start_brain_local.ps1
# Safely start Brain V9 local services (8091 Brain API and/or 8092 Dashboard) detached.
# Front: FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01
#
# Safety:
# - Token is read ONLY from $env:BRAIN_ADMIN_TOKEN; NEVER hardcoded; redacted in output.
# - Uses the canonical safe launcher start_safe_server.py for 8091 (no hardcoded secrets).
# - Starts dashboard via uvicorn -c on 8092; writes PID to dashboard_only_8092.pid.
# - Does NOT touch memory/FAISS/broker/trading/governance/source files.
# - Does NOT run any git command.
# - Refuses to start if the target port is already listening (idempotent) unless -Force.

[CmdletBinding()]
param(
    [switch]$BrainOnly,     # start only 8091
    [switch]$DashboardOnly, # start only 8092
    [switch]$Force          # start even if already listening
)

$ErrorActionPreference = "Stop"
$Root = "C:\AI_VAULT_CANONICAL"
$LogDir = Join-Path $Root "tmp_agent\brain_v9"
$env:PYTHONPATH = $Root
$env:PYTHONIOENCODING = "utf-8"

function Redact-Token([string]$t) {
    if ([string]::IsNullOrEmpty($t)) { return "<none>" }
    if ($t.Length -le 8) { return "***" }
    return $t.Substring(0,8) + "***REDACTED"
}

function Is-Listening([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Start-Brain() {
    if (Is-Listening 8091) {
        if ($Force) { "8091 already listening; -Force: leaving existing process in place (no double-start)" }
        else { "8091 already listening. Skipping (use -Force to override, which still will not double-bind)." }
        return
    }
    if (-not $env:BRAIN_ADMIN_TOKEN) {
        Write-Warning "BRAIN_ADMIN_TOKEN not set. 8091 will start but token-gated endpoints will reject calls."
    }
    $proc = Start-Process -FilePath "python" `
        -ArgumentList "tmp_agent/brain_v9/start_safe_server.py" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden -PassThru
    "8091 STARTED: PID=$($proc.Id) (start_safe_server.py) token=" + (Redact-Token $env:BRAIN_ADMIN_TOKEN)
}

function Start-Dashboard() {
    if (Is-Listening 8092) {
        if ($Force) { "8092 already listening; -Force: leaving existing process in place" }
        else { "8092 already listening. Skipping." }
        return
    }
    $cmd = "import uvicorn; uvicorn.run('tmp_agent.brain_v9.dashboard.dashboard_app:app', host='127.0.0.1', port=8092, log_level='info', reload=False)"
    $logOut = Join-Path $LogDir "dashboard_only_8092.log"
    $logErr = Join-Path $LogDir "dashboard_only_8092.err.log"
    $pidFile = Join-Path $LogDir "dashboard_only_8092.pid"
    $proc = Start-Process -FilePath "python" -ArgumentList @("-c", $cmd) `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $logOut `
        -RedirectStandardError $logErr `
        -WindowStyle Hidden -PassThru
    $proc.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline
    "8092 STARTED: PID=$($proc.Id) (dashboard_app:app) -> $pidFile"
}

if ($BrainOnly -and -not $DashboardOnly) {
    Start-Brain
} elseif ($DashboardOnly -and -not $BrainOnly) {
    Start-Dashboard
} else {
    Start-Brain
    Start-Sleep -Seconds 3
    Start-Dashboard
}

"start_brain_local complete. Verify with status_brain_local.ps1."
