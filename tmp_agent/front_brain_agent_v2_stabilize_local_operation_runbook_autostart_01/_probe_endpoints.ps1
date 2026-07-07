# _probe_endpoints.ps1 — read-only endpoint probe for Phase 2
# Reads token from $env:BRAIN_ADMIN_TOKEN if set; otherwise uses the local
# development TEST token that the running services were started with.
# Token is NEVER printed in full; only a redacted prefix is shown.

$ErrorActionPreference = "Continue"

if (-not $env:BRAIN_ADMIN_TOKEN -or $env:BRAIN_ADMIN_TOKEN.Trim() -eq "") {
    Write-Error "BRAIN_ADMIN_TOKEN is required. Set it in your environment."
    exit 2
}

function Redact-Token([string]$t) {
    if ([string]::IsNullOrEmpty($t)) { return "<none>" }
    if ($t.Length -le 8) { return "***" }
    return $t.Substring(0,8) + "***REDACTED"
}

function Probe([string]$url, [bool]$withToken) {
    $obj = [ordered]@{
        endpoint = $url
        auth_required = $false
        token_redacted = $true
    }
    try {
        $headers = @{}
        if ($withToken) {
            $headers["X-Brain-Token"] = $env:BRAIN_ADMIN_TOKEN
        }
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers $headers
        $obj.status_code = $r.StatusCode
        $obj.exists = $true
        $body = $r.Content
        if ($body.Length -gt 220) { $body = $body.Substring(0,220) + "..." }
        $obj.response_type = if ($r.Headers["Content-Type"]) { $r.Headers["Content-Type"] } else { "unknown" }
        $obj.body_preview = $body
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        $obj.status_code = $code
        if ($code -eq 401 -or $code -eq 403) { $obj.auth_required = $true }
        if ($code -eq 404 -or $code -eq 405) { $obj.exists = $false } else { $obj.exists = $true }
        $obj.error = $_.Exception.Message
    }
    return $obj
}

$results = [ordered]@{ results = @() }

# Brain API 8091
$results.results += (Probe "http://127.0.0.1:8091/health" $false)
$results.results += (Probe "http://127.0.0.1:8091/v2/agent/status" $true)
$results.results += (Probe "http://127.0.0.1:8091/v2/agent/capabilities" $true)

# Dashboard 8092
$results.results += (Probe "http://127.0.0.1:8092/" $false)
$results.results += (Probe "http://127.0.0.1:8092/health" $false)
$results.results += (Probe "http://127.0.0.1:8092/brain-dashboard/status" $false)
$results.results += (Probe "http://127.0.0.1:8092/brain-dashboard/agent-v2/status" $false)
$results.results += (Probe "http://127.0.0.1:8092/brain-dashboard/chat" $false)

# Legacy 8070
$results.results += (Probe "http://127.0.0.1:8070/" $false)

$results.token_used_redacted = (Redact-Token $env:BRAIN_ADMIN_TOKEN)
$results.timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")

$results | ConvertTo-Json -Depth 6
