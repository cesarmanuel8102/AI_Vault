#Requires -RunAsAdministrator
param(
    [string]$Root = "C:\AI_VAULT_CANONICAL",
    [int]$Port = 8091
)

$ErrorActionPreference = "Continue"
$logDir = "$Root\tmp_agent\runtime"
$null = New-Item -ItemType Directory -Force -Path $logDir

function Write-Log {
    param([string]$msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $msg"
    Write-Host $line
    Add-Content -Path "$logDir\probe_agent_v2_live.log" -Value $line
}

Write-Log "=== Agent V2 Live Probe (8091) ==="

$results = @{
    timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
    port = $Port
    endpoints = @{}
}

# Probe endpoints
$endpoints = @(
    @{ Method = 'GET'; Url = "http://127.0.0.1:$Port/health" }
    @{ Method = 'GET'; Url = "http://127.0.0.1:$Port/v2/agent/status" }
    @{ Method = 'GET'; Url = "http://127.0.0.1:$Port/v2/agent/capabilities" }
    @{ Method = 'POST'; Url = "http://127.0.0.1:$Port/v2/chat/agent"; Body = '{"message":"Hello from probe","mode":"read_only","user_id":"probe_script"}' }
)

foreach ($ep in $endpoints) {
    try {
        if ($ep.Method -eq 'POST') {
            $resp = Invoke-RestMethod -Uri $ep.Url -Method POST -Body $ep.Body -ContentType 'application/json' -TimeoutSec 15
        } else {
            $resp = Invoke-RestMethod -Uri $ep.Url -Method GET -TimeoutSec 10
        }
        $results.endpoints[$ep.Url] = @{
            ok = $true
            status = 200
            response = if ($resp -is [string]) { $resp.Substring(0, [Math]::Min(200, $resp.Length)) } else { $resp | ConvertTo-Json -Compress -Depth 2 }
        }
        Write-Log "OK $($ep.Url)"
    } catch {
        $results.endpoints[$ep.Url] = @{
            ok = $false
            error = $_.Exception.Message
        }
        Write-Log "FAIL $($ep.Url): $_"
    }
}

# Save results
$jsonPath = "$logDir\probe_agent_v2_live.json"
$results | ConvertTo-Json -Depth 5 | Set-Content -Path $jsonPath
Write-Log "Results saved to $jsonPath"
Write-Log "=== Probe Complete ==="
