$conn = Get-NetTCPConnection -LocalPort 8091 -ErrorAction SilentlyContinue
if ($conn) {
    Write-Output "PORT_8091_BOUND"
    $conn | Format-Table LocalAddress, LocalPort, State, OwningProcess -AutoSize
} else {
    Write-Output "PORT_8091_FREE"
}

$conn2 = Get-NetTCPConnection -LocalPort 8092 -ErrorAction SilentlyContinue
if ($conn2) {
    Write-Output "PORT_8092_BOUND"
    $conn2 | Format-Table LocalAddress, LocalPort, State, OwningProcess -AutoSize
} else {
    Write-Output "PORT_8092_FREE"
}

$procs = Get-Process -Id 107856, 13196, 126276 -ErrorAction SilentlyContinue
if ($procs) {
    Write-Output "LIVE_PROCS:"
    $procs | Format-Table Id, ProcessName, StartTime -AutoSize
} else {
    Write-Output "NO_TRACKED_PROCS_LIVE"
}
