# status_brain_local.ps1
# Read-only status for Brain V9 local services (8091 Brain API, 8092 Dashboard).
# Front: FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01
#
# Safety:
# - Strictly read-only. Starts/stops nothing. Modifies nothing.
# - Token is read from $env:BRAIN_ADMIN_TOKEN and NEVER printed in full (only redacted prefix).
# - Never kills any process.

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Root = "C:\AI_VAULT_CANONICAL"

function Redact-Token([string]$t) {
    if ([string]::IsNullOrEmpty($t)) { return "<none>" }
    if ($t.Length -le 8) { return "***" }
    return $t.Substring(0,8) + "***REDACTED"
}

Write-Output "=== Brain local status ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')) ==="
Write-Output "Workspace: $Root"

Write-Output ""
Write-Output "--- Listeners (8091 / 8092 / 8070) ---"
$ports = @(8091, 8092, 8070)
foreach ($p in $ports) {
    $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if ($c) {
        $owner = $c.OwningProcess
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue
        $cmd = if ($proc) { $proc.CommandLine } else { "<unknown>" }
        if ($cmd.Length -gt 110) { $cmd = $cmd.Substring(0,110) + "..." }
        "{0}  LISTEN  owner PID={1}  cmd={2}" -f $p, $owner, $cmd
    } else {
        "{0}  (not listening)" -f $p
    }
}

Write-Output ""
Write-Output "--- PID files ---"
$pidDir = Join-Path $Root "tmp_agent\brain_v9"
Get-ChildItem -Path $pidDir -Filter "*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
    $rec = (Get-Content $_.FullName -Raw).Trim()
    $alive = [bool](Get-Process -Id $rec -ErrorAction SilentlyContinue)
    "{0,-55} recordedPID={1,-8} alive={2,-5} verdict={3}" -f $_.Name, $rec, $alive, $(if($alive){'VALID'}else{'STALE'})
}

Write-Output ""
Write-Output "--- Health endpoints ---"
function Probe([string]$u, [switch]$Token) {
    try {
        $h = @{}
        if ($Token -and $env:BRAIN_ADMIN_TOKEN) { $h["X-Brain-Token"] = $env:BRAIN_ADMIN_TOKEN }
        $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 6 -Headers $h
        $body = $r.Content
        if ($body.Length -gt 90) { $body = $body.Substring(0,90) + "..." }
        "{0,-3}  {1}  body={2}" -f $r.StatusCode, $u, $body
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        "{0}  {1}  ({2})" -f $code, $u, $_.Exception.Message
    }
}
Probe "http://127.0.0.1:8091/health"
Probe "http://127.0.0.1:8092/health"
Probe "http://127.0.0.1:8092/brain-dashboard/status"
if ($env:BRAIN_ADMIN_TOKEN) {
    Probe "http://127.0.0.1:8091/v2/agent/status" -Token
    Probe "http://127.0.0.1:8091/v2/agent/capabilities" -Token
} else {
    "SKIP 8091/v2/agent/* (set `$env:BRAIN_ADMIN_TOKEN to probe token-gated endpoints)"
}

Write-Output ""
Write-Output "Token: " + (Redact-Token $env:BRAIN_ADMIN_TOKEN)
Write-Output "=== status complete ==="
