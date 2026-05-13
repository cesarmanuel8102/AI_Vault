$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "PID: $($proc.Id)"
        Write-Host "Name: $($proc.ProcessName)"
        Write-Host "StartTime: $($proc.StartTime)"
        Write-Host "CommandLine: $($proc.CommandLine)"
    }
} else {
    Write-Host "No process on 8090"
}
