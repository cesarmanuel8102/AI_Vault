Write-Host "=== Port 8090 ==="
$conns = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
if ($conns) { $conns | Format-Table } else { Write-Host "  none listening on 8090" }

Write-Host "=== Python procs ==="
Get-Process -Name python* -ErrorAction SilentlyContinue | Select-Object Id, StartTime | Format-Table

Write-Host "=== Health try ==="
try {
    $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/health' -TimeoutSec 5
    Write-Host "OK status=$($h.status)"
} catch { Write-Host "FAIL: $($_.Exception.Message)" }
