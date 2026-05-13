# R15 + R20 smoke test
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"

Write-Host "=== R15: read_file on a directory (PermissionError/IsADirectory) ===" -ForegroundColor Cyan
$body = @{
    tool = "read_file"
    args = @{ path = "C:/AI_VAULT/tmp_agent/brain_v9" }
} | ConvertTo-Json -Compress
try {
    $r1 = Invoke-RestMethod -Uri "$base/tools/run" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30
    $r1 | ConvertTo-Json -Depth 6
} catch {
    Write-Host "endpoint /tools/run not available, trying via chat" -ForegroundColor Yellow
    $chatBody = @{ message = "Lee el archivo C:/AI_VAULT/tmp_agent/brain_v9 y dime su contenido"; session_id = "smoke_r15" } | ConvertTo-Json -Compress
    $r1 = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $chatBody -ContentType "application/json" -TimeoutSec 120
    $r1 | ConvertTo-Json -Depth 4
}

Write-Host ""
Write-Host "=== R15: tail event_log for capability.failed with new payload ===" -ForegroundColor Cyan
$logPath = "C:/AI_VAULT/state/events/event_log.jsonl"
if (Test-Path $logPath) {
    Get-Content $logPath -Tail 10 | ForEach-Object {
        if ($_ -match "capability.failed") {
            try {
                $obj = $_ | ConvertFrom-Json
                Write-Host ("  evt={0} cap={1} err_type={2} hint={3}" -f $obj.event, $obj.payload.capability, $obj.payload.error_type, $obj.payload.hint)
            } catch { Write-Host $_ }
        }
    }
}

Write-Host ""
Write-Host "=== R20: scan_local_network with auto_chunk on /24 ===" -ForegroundColor Cyan
$body2 = @{
    tool = "scan_local_network"
    args = @{ cidr = "192.168.1.0/24"; timeout = 0.3; max_hosts = 32; auto_chunk = $true }
} | ConvertTo-Json -Compress
try {
    $r2 = Invoke-RestMethod -Uri "$base/tools/run" -Method Post -Body $body2 -ContentType "application/json" -TimeoutSec 90
    $r2 | ConvertTo-Json -Depth 4
} catch {
    Write-Host "ERR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== R20: legacy mode (auto_chunk=False) on /24 should still error ===" -ForegroundColor Cyan
$body3 = @{
    tool = "scan_local_network"
    args = @{ cidr = "192.168.1.0/24"; timeout = 0.3; max_hosts = 32; auto_chunk = $false }
} | ConvertTo-Json -Compress
try {
    $r3 = Invoke-RestMethod -Uri "$base/tools/run" -Method Post -Body $body3 -ContentType "application/json" -TimeoutSec 30
    $r3 | ConvertTo-Json -Depth 4
} catch {
    Write-Host "ERR: $($_.Exception.Message)" -ForegroundColor Red
}
