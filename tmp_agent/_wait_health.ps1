Start-Sleep -Seconds 30
try {
    $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/health' -TimeoutSec 5
    Write-Host "status=$($h.status) safe_mode=$($h.safe_mode)"
} catch {
    Write-Host "DOWN: $($_.Exception.Message)"
}
