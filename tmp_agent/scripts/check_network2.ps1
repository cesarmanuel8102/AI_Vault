# Check network usage per process and ARP table for devices on local network
Write-Host "`n=== OTROS DISPOSITIVOS EN TU RED ===" -ForegroundColor Yellow
arp -a | Where-Object { $_ -match '192\.168\.' } 

Write-Host "`n=== PROCESOS CON CONEXIONES ACTIVAS AHORA ===" -ForegroundColor Yellow
Get-NetTCPConnection -State Established | 
    Where-Object { $_.RemoteAddress -notmatch '^(127\.|::1|0\.)' } |
    ForEach-Object {
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        [PSCustomObject]@{
            Process = $proc.Name
            PID = $_.OwningProcess
            Remote = $_.RemoteAddress
            Port = $_.RemotePort
            State = $_.State
        }
    } | Sort-Object Process | Format-Table -AutoSize

Write-Host "`n=== BANDWIDTH POR PROCESO (bytes sent/received) ===" -ForegroundColor Yellow
Get-Process | Where-Object { $_.Id -ne 0 } | 
    Sort-Object WorkingSet64 -Descending | 
    Select-Object -First 15 Name, Id, 
        @{N='RAM_MB';E={[math]::Round($_.WorkingSet64/1MB,0)}},
        @{N='CPU_sec';E={[math]::Round($_.CPU,1)}} |
    Format-Table -AutoSize

Write-Host "`n=== NETSTAT - CONEXIONES UDP (streaming/video) ===" -ForegroundColor Yellow
Get-NetUDPEndpoint | 
    ForEach-Object {
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        if ($proc.Name -and $proc.Name -ne 'svchost') {
            [PSCustomObject]@{
                Process = $proc.Name
                PID = $_.OwningProcess
                LocalPort = $_.LocalPort
            }
        }
    } | Sort-Object Process -Unique | Format-Table -AutoSize
