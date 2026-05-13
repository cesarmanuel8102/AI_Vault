Write-Host "=== All powershell processes ==="
Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" |
    Select-Object ProcessId, ParentProcessId, CommandLine | Format-List

Write-Host "`n=== Process listening on 8090 ==="
$conns = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $conns) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
    if ($p) {
        Write-Host "PID=$($p.ProcessId) PPID=$($p.ParentProcessId) Name=$($p.Name)"
        Write-Host "CMD: $($p.CommandLine)"
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($parent) {
            Write-Host "PARENT: PID=$($parent.ProcessId) Name=$($parent.Name)"
            Write-Host "PARENT CMD: $($parent.CommandLine)"
        }
    }
}

Write-Host "`n=== Tail autostart log ==="
Get-Content C:\AI_VAULT\tmp_agent\autostart_watchdog.log -Tail 20
