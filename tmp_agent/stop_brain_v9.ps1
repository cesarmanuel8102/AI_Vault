$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn.OwningProcess
    Write-Host "Killing Brain V9 PID: $pid"
    Stop-Process -Id $pid -Force
    Start-Sleep -Seconds 2
    Write-Host "Stopped"
} else {
    Write-Host "No process on port 8090"
}
