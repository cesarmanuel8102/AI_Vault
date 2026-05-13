try {
  $r = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 5
  Write-Host "OK status=$($r.status) safe=$($r.safe_mode) uptime=$($r.uptime_seconds)"
} catch {
  Write-Host "DOWN: $($_.Exception.Message)"
}
$bp = Get-Process python -ErrorAction SilentlyContinue
foreach ($x in $bp) {
  $age = (New-TimeSpan -Start $x.StartTime -End (Get-Date)).TotalSeconds
  Write-Host ("PID={0} ageSec={1:N0}" -f $x.Id, $age)
}
