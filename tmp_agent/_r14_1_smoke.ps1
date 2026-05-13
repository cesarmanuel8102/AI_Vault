$base = "http://127.0.0.1:8090"

# Direct call to get_dashboard_data via Python tool harness is hard via HTTP.
# Instead, trigger via /chat with a query that will route to it, and observe coverage.

# Wait a bit for any background callers (sample_accumulator) to fire
Start-Sleep -Seconds 30

Write-Host "===== /tools/coverage after 30s warmup ====="
$r = Invoke-RestMethod -Uri "$base/tools/coverage" -Method Get -TimeoutSec 10
$r.totals | Format-List
$r.tools.PSObject.Properties | Where-Object { $_.Name -eq "get_dashboard_data" } | ForEach-Object {
    $s = $_.Value
    Write-Host ("get_dashboard_data: inv={0} succ={1} fail={2} success_rate={3} last_error={4}" -f $s.invocations, $s.successes, $s.failures, $s.success_rate, $s.last_error)
}
