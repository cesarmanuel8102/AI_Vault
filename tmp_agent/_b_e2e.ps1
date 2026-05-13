$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"

function Show-Patterns {
    try {
        $r = Invoke-RestMethod -Uri "$base/brain/learned/patterns" -TimeoutSec 5
        Write-Host ("[patterns] count={0}" -f $r.count) -ForegroundColor Cyan
        foreach ($p in $r.patterns) {
            Write-Host ("  - {0} | tool={1} -> {2} | conf={3} | passes={4} fails={5} disabled={6}" -f `
                $p.id, $p.tool_class, $p.correction.to_tool, $p.confidence, `
                $p.validation.passes, $p.validation.fails, $p.disabled)
        }
    } catch { Write-Host ("[patterns ERR] {0}" -f $_.Exception.Message) -ForegroundColor Red }
}

function Show-Counters {
    try {
        $c = (Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 5).live_module_counters
        $rel = $c.PSObject.Properties | Where-Object { $_.Name -match "learned|self_test" }
        Write-Host "[counters relevant]" -ForegroundColor Cyan
        foreach ($r in $rel) { Write-Host ("  {0} = {1}" -f $r.Name, $r.Value) }
        if (-not $rel) { Write-Host "  (none yet)" }
    } catch { Write-Host ("[counters ERR] {0}" -f $_.Exception.Message) -ForegroundColor Red }
}

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "B-Sprint META-LOOP E2E TEST" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

Write-Host ""
Write-Host "--- BEFORE ---" -ForegroundColor Green
Show-Patterns
Show-Counters

# Synthetic failure: run_command tried to invoke a PowerShell cmdlet directly.
# This is NOT covered by R24v2 (no `$` in error). LLM should learn:
#   "is not recognized" + cmd looks like Get-XXX -> rewrite to run_powershell.
$body = @{
    tool       = "run_command"
    args       = @{ cmd = "Get-Service spooler" }
    error_text = "'Get-Service' is not recognized as an internal or external command, operable program or batch file. exit_code=1"
} | ConvertTo-Json -Compress

Write-Host ""
Write-Host "--- TEST 1: synthetic failure (Get-Service via run_command) ---" -ForegroundColor Yellow
Write-Host ("payload: {0}" -f $body)

try {
    $resp = Invoke-RestMethod -Uri "$base/brain/learned/test_simulate" `
        -Method POST -Body $body -ContentType "application/json" -TimeoutSec 90
    Write-Host ""
    Write-Host ("OUTCOME: {0}" -f $resp.outcome) -ForegroundColor Magenta
    Write-Host "TRACE:" -ForegroundColor Magenta
    $resp.trace | ConvertTo-Json -Depth 6
} catch {
    Write-Host ("REQUEST FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
    if ($_.ErrorDetails) { Write-Host $_.ErrorDetails.Message }
}

Write-Host ""
Write-Host "--- AFTER TEST 1 ---" -ForegroundColor Green
Show-Patterns
Show-Counters

Write-Host ""
Write-Host "--- TEST 2: same failure again (should HIT existing pattern) ---" -ForegroundColor Yellow
try {
    $resp2 = Invoke-RestMethod -Uri "$base/brain/learned/test_simulate" `
        -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
    Write-Host ("OUTCOME: {0}" -f $resp2.outcome) -ForegroundColor Magenta
    $resp2.trace | ConvertTo-Json -Depth 4
} catch {
    Write-Host ("REQUEST FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
}

Write-Host ""
Write-Host "--- FINAL STATE ---" -ForegroundColor Green
Show-Patterns
Show-Counters
