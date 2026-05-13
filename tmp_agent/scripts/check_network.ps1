$connections = Get-NetTCPConnection -State Established | Where-Object { $_.RemoteAddress -notmatch '^(127\.|::1|0\.)' }

$grouped = $connections | ForEach-Object {
    $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        PID = $_.OwningProcess
        Process = $proc.Name
        Remote = $_.RemoteAddress
        Port = $_.RemotePort
    }
}

Write-Host "`n=== CONNECTIONS PER PROCESS ===" -ForegroundColor Yellow
$grouped | Group-Object Process | Sort-Object Count -Descending | Select-Object Name, Count | Format-Table -AutoSize

Write-Host "`n=== TOP BANDWIDTH CONSUMERS (by connection count) ===" -ForegroundColor Yellow
$grouped | Group-Object Process | Sort-Object Count -Descending | Select-Object -First 10 | ForEach-Object {
    $procName = $_.Name
    $count = $_.Count
    $remotes = ($_.Group | Select-Object -ExpandProperty Remote -Unique) -join ", "
    Write-Host "$procName : $count connections -> $remotes"
}

Write-Host "`n=== ALL REMOTE ENDPOINTS ===" -ForegroundColor Yellow
$grouped | Select-Object Process, Remote, Port | Sort-Object Process | Format-Table -AutoSize
