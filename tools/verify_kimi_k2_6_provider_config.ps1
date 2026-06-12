[CmdletBinding()]
param(
    [string]$OutDir = "tmp_agent/front_kimi_k2_6_cloud_provider_config_runbook_01",
    [switch]$LiveProbe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force $OutDir | Out-Null

function Get-EnvInfo {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    $scope = "Process"
    if ([string]::IsNullOrWhiteSpace($value)) { $value = [Environment]::GetEnvironmentVariable($Name, "User"); $scope = "User" }
    if ([string]::IsNullOrWhiteSpace($value)) { $value = [Environment]::GetEnvironmentVariable($Name, "Machine"); $scope = "Machine" }
    if ([string]::IsNullOrWhiteSpace($value)) { $scope = "Unknown" }
    [ordered]@{ present = -not [string]::IsNullOrWhiteSpace($value); length = if ($value) { $value.Length } else { 0 }; source_scope = $scope; value_redacted = $true }
}

$modelTag = [Environment]::GetEnvironmentVariable("KIMI_OLLAMA_MODEL", "Process")
if ([string]::IsNullOrWhiteSpace($modelTag)) { $modelTag = [Environment]::GetEnvironmentVariable("KIMI_OLLAMA_MODEL", "User") }
if ([string]::IsNullOrWhiteSpace($modelTag)) { $modelTag = "kimi-k2.6:cloud" }

$ollamaTags = @()
$ollamaReachable = $false
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
    $ollamaReachable = $true
    $ollamaTags = @($tags.models | ForEach-Object { $_.name })
} catch {}

$brainModelsStatus = "NOT_TESTED"
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8091/v1/models" -TimeoutSec 8
    $brainModelsStatus = "AVAILABLE"
} catch {
    $brainModelsStatus = "UNAVAILABLE"
}

$liveProbeResult = $null
if ($LiveProbe -and $ollamaReachable -and ($ollamaTags -contains $modelTag)) {
    try {
        $body = @{ model = $modelTag; messages = @(@{ role = "user"; content = "Say OK." }); stream = $false } | ConvertTo-Json -Depth 5
        $started = Get-Date
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 45
        $elapsedMs = [int]((Get-Date) - $started).TotalMilliseconds
        $content = ""
        if ($resp.message -and $resp.message.content) { $content = [string]$resp.message.content }
        $liveProbeResult = [ordered]@{ status = if ($content.Trim().Length -gt 0) { "KIMI_CONFIG_VERIFIED" } else { "EMPTY_RESPONSE" }; latency_ms = $elapsedMs; non_empty_response = ($content.Trim().Length -gt 0); response_length = $content.Length; secrets_exposed = $false }
    } catch {
        $liveProbeResult = [ordered]@{ status = "PROBE_FAILED_REDACTED"; error_type = $_.Exception.GetType().Name; secrets_exposed = $false }
    }
}

$status = "KIMI_CONFIG_MISSING"
if ($ollamaReachable -and ($ollamaTags -contains $modelTag)) { $status = "KIMI_CONFIG_PRESENT_NOT_BENCHMARKED" }
if ($liveProbeResult -and $liveProbeResult.status -eq "KIMI_CONFIG_VERIFIED") { $status = "KIMI_CONFIG_VERIFIED" }

$report = [ordered]@{
    status = $status
    model_tag = $modelTag
    model_tag_present_in_ollama = ($ollamaTags -contains $modelTag)
    kimi_k2_5_cloud_present = ($ollamaTags -contains "kimi-k2.5:cloud")
    kimi_k2_6_cloud_present = ($ollamaTags -contains "kimi-k2.6:cloud")
    ollama_reachable = $ollamaReachable
    brain_models_status = $brainModelsStatus
    env = [ordered]@{
        KIMI_OLLAMA_MODEL = Get-EnvInfo "KIMI_OLLAMA_MODEL"
        KIMI_API_KEY = Get-EnvInfo "KIMI_API_KEY"
        MOONSHOT_API_KEY = Get-EnvInfo "MOONSHOT_API_KEY"
    }
    live_probe = $liveProbeResult
    secrets_exposed = $false
    headers_printed = $false
    env_file_written = $false
}

$jsonPath = Join-Path $OutDir "provider_config_verify.json"
$mdPath = Join-Path $OutDir "provider_config_verify.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $jsonPath -Encoding UTF8
@"
# Kimi Ollama Cloud Provider Verify

- status: ``$($report.status)``
- model_tag: ``$($report.model_tag)``
- model_tag_present_in_ollama: ``$($report.model_tag_present_in_ollama)``
- kimi_k2_5_cloud_present: ``$($report.kimi_k2_5_cloud_present)``
- kimi_k2_6_cloud_present: ``$($report.kimi_k2_6_cloud_present)``
- ollama_reachable: ``$($report.ollama_reachable)``
- brain_models_status: ``$($report.brain_models_status)``
- secrets_exposed: ``false``
- env_file_written: ``false``
"@ | Set-Content -Path $mdPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8
