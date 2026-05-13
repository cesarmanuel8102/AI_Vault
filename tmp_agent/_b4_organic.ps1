$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"

function Show-Patterns {
    try {
        $r = Invoke-RestMethod -Uri "$base/brain/learned/patterns" -TimeoutSec 5
        Write-Host ("[patterns] count={0}" -f $r.count) -ForegroundColor Cyan
        foreach ($p in $r.patterns) {
            Write-Host ("  - {0} | {1} -> {2} | conf={3} | passes={4}" -f `
                $p.id, $p.tool_class, $p.correction.to_tool, $p.confidence, $p.validation.passes)
        }
    } catch { Write-Host "[patterns ERR] $($_.Exception.Message)" -ForegroundColor Red }
}

function Show-Counters {
    try {
        $c = (Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 5).live_module_counters
        $rel = $c.PSObject.Properties | Where-Object { $_.Name -match "learned|self_test|auto_rewrite" }
        Write-Host "[counters]" -ForegroundColor Cyan
        foreach ($r in $rel) { Write-Host ("  {0} = {1}" -f $r.Name, $r.Value) }
        if (-not $rel) { Write-Host "  (none)" }
    } catch {}
}

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "B4: ORGANIC E2E - trigger meta-loop via /chat" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "--- BEFORE ---" -ForegroundColor Green
Show-Patterns
Show-Counters

# This task will force the agent to try `run_command Get-Process` which will fail
# with "is not recognized" on cmd.exe, then the meta-loop should kick in.
$chatBody = @{
    session_id = "b4_organic_test"
    message = "Usa run_command para ejecutar 'Get-Process explorer'. NO uses run_powershell, quiero que uses run_command directamente."
} | ConvertTo-Json -Compress

Write-Host ""
Write-Host "--- Sending chat request ---" -ForegroundColor Yellow
Write-Host ("body: {0}" -f $chatBody)
$t0 = Get-Date
try {
    $resp = Invoke-RestMethod -Uri "$base/chat" -Method POST -Body $chatBody `
        -ContentType "application/json" -TimeoutSec 180
    $ms = ((Get-Date) - $t0).TotalMilliseconds
    Write-Host ("Response in {0:N0}ms" -f $ms) -ForegroundColor Cyan
    Write-Host ("success={0}" -f $resp.success) -ForegroundColor Magenta
    Write-Host "response preview:" -ForegroundColor Magenta
    Write-Host ($resp.response.Substring(0, [Math]::Min(800, $resp.response.Length)))
} catch {
    Write-Host ("CHAT FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
}

Write-Host ""
Write-Host "--- AFTER CHAT ---" -ForegroundColor Green
Show-Patterns
Show-Counters

Write-Host ""
Write-Host "--- Check events for learned_pattern_* ---" -ForegroundColor Yellow
try {
    $log = Get-ChildItem C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl -ErrorAction Stop
    $lines = Get-Content $log.FullName -Tail 50 | Where-Object { $_ -match "learned_pattern" }
    if ($lines) {
        foreach ($l in $lines) { Write-Host $l }
    } else {
        Write-Host "(no learned_pattern events in last 50 lines)"
    }
} catch { Write-Host "(event log not found)" }
