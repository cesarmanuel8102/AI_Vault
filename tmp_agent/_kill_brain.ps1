$conns = Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue
if ($conns) {
    $pidList = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pidList) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        Write-Host "killed PID $p"
    }
}
Write-Host "waiting for watchdog to respawn..."
Start-Sleep -Seconds 90
$h = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 30
$h | ConvertTo-Json
