try {
    $h = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 30
    Write-Host "status=$($h.status) safe_mode=$($h.safe_mode) god_mode=$($h.god_mode) uptime=$($h.uptime_seconds)"
} catch {
    Write-Host "ERR: $($_.Exception.Message)"
}
