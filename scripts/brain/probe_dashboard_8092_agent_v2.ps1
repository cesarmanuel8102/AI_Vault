#Requires -RunAsAdministrator
param(
    [string]$Root = "C:\AI_VAULT_CANONICAL",
    [int]$Port = 8092
)

$ErrorActionPreference = "Continue"
$logDir = "$Root\tmp_agent\runtime"
$null = New-Item -ItemType Directory -Force -Path $logDir

function Write-Log {
    param([string]$msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $msg"
    Write-Host $line
    Add-Content -Path "$logDir\probe_dashboard_8092_agent_v2.log" -Value $line
}

Write-Log "=== Dashboard 8092 Agent V2 Probe ==="

$results = @{
    timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
    port = $Port
    endpoints = @{}
    zombie_detected = $false
}

# Check for zombie process
$listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
foreach ($conn in $listeners) {
    try {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction Stop
        Write-Log "Process found: PID=$($conn.OwningProcess) Name=$($proc.ProcessName)"
    } catch {
        Write-Log "ZOMBIE DETECTED: Port $Port has PID $($conn.OwningProcess) but process not found"
        $results.zombie_detected = $true
    }
}

# Probe endpoints
$endpoints = @(
    @{ Method = 'GET'; Url = "http://127.0.0.1:$Port/health" }
    @{ Method = 'GET'; Url = "http://127.0.0.1:$Port/brain-dashboard/status" }
    @{ Method = 'GET'; Url = "http://127.0.0.1:$Port/brain-dashboard/agent-v2/status" }
)

foreach ($ep in $endpoints) {
    try {
        $resp = Invoke-RestMethod -Uri $ep.Url -Method GET -TimeoutSec 10
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
$jsonPath = "$logDir\probe_dashboard_8092_agent_v2.json"
$results | ConvertTo-Json -Depth 5 | Set-Content -Path $jsonPath
Write-Log "Results saved to $jsonPath"
Write-Log "=== Probe Complete ==="
