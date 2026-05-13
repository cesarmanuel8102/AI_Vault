$base = "http://127.0.0.1:8090"
$body = @{
    tool       = "run_command"
    args       = @{ cmd = "Get-Service spooler" }
    error_text = "'Get-Service' is not recognized as an internal or external command, operable program or batch file. exit_code=1"
} | ConvertTo-Json -Compress

Write-Host "--- Lookup hit test (3rd call, pattern already persisted) ---" -ForegroundColor Yellow
$t0 = Get-Date
$resp = Invoke-RestMethod -Uri "$base/brain/learned/test_simulate" `
    -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
$ms = ((Get-Date) - $t0).TotalMilliseconds
Write-Host ("Response in {0:N0}ms" -f $ms) -ForegroundColor Cyan
Write-Host ("OUTCOME: {0}" -f $resp.outcome) -ForegroundColor Magenta
$resp.trace | ConvertTo-Json -Depth 5

Write-Host ""
Write-Host "--- Counters (should show learned_pattern_hit) ---" -ForegroundColor Yellow
$c = (Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 5).live_module_counters
$c.PSObject.Properties | Where-Object { $_.Name -match "learned|self_test" } | ForEach-Object {
    Write-Host ("  {0} = {1}" -f $_.Name, $_.Value)
}

Write-Host ""
Write-Host "--- Pattern detail (should show use_count=1, last_used_utc set) ---" -ForegroundColor Yellow
$p = Invoke-RestMethod -Uri "$base/brain/learned/patterns" -TimeoutSec 5
$p.patterns[0] | ConvertTo-Json -Depth 5
