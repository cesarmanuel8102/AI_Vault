# Robust kill via CIM Terminate (works around Stop-Process ACL issues)
$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    $pid_target = $conn.OwningProcess
    Write-Host "Killing brain PID $pid_target via CIM Terminate"
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid_target" -ErrorAction SilentlyContinue
    if ($proc) {
        $r = Invoke-CimMethod -InputObject $proc -MethodName Terminate
        Write-Host "Terminate ReturnValue: $($r.ReturnValue)"
    } else {
        Write-Host "CIM lookup failed"
    }
} else {
    Write-Host "No brain on 8090"
}
Write-Host "Waiting 50s for watchdog respawn..."
Start-Sleep 50
try {
    $h = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 30
    $newConn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Host "Brain back: status=$($h.status) safe_mode=$($h.safe_mode) NEW_PID=$($newConn.OwningProcess)"
} catch {
    Write-Host "Still down: $($_.Exception.Message)"
}
