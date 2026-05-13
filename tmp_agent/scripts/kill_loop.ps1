# Kill the loop runner process (started recently)
$procs = Get-Process python -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    if ($p.StartTime -gt (Get-Date).AddMinutes(-15)) {
        Write-Output "Killing PID $($p.Id) started at $($p.StartTime)"
        Stop-Process -Id $p.Id -Force
    }
}
Write-Output "Done"
