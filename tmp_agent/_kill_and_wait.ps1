$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Write-Host "Killing brain PID $($conn.OwningProcess)"
    Stop-Process -Id $conn.OwningProcess -Force
} else {
    Write-Host "No brain on 8090"
}
Write-Host "Waiting for watchdog respawn (60s)..."
Start-Sleep 60
try {
    $h = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 30
    Write-Host "Brain back: status=$($h.status) safe_mode=$($h.safe_mode)"
} catch {
    Write-Host "Still down: $($_.Exception.Message)"
}
