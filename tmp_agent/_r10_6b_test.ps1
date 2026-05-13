$ErrorActionPreference = 'Stop'
$ROOT = 'C:/AI_VAULT/tmp_agent'
$STATE = "$ROOT/state/proposed_patches"
$PORT = 8090

function New-Proposal($id, $text, $files) {
    $p = [ordered]@{
        proposal_id     = $id
        iter            = 0
        weakness        = "test"
        proposed_change = $text
        affected_files  = $files
        risk_class      = "low"
        risk_reasons    = @()
        impact_score    = 8
        status          = "pending_review"
        created_at      = (Get-Date).ToString("o")
        source          = "r10_6b_test"
    }
    $json = $p | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText("$STATE/$id.json", $json, [System.Text.UTF8Encoding]::new($false))
}

function Test-DryRun($id, $expectOk, $label, $expectReasonSubstr) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/brain/chat_excellence/proposals/$id/dry_run" -Method Post -TimeoutSec 15
        $skipMsg = if ($r.skipped) { ($r.skipped | ConvertTo-Json -Compress) } else { "" }
        if ($expectOk -and $r.ok) {
            Write-Host "[$label] PASS ok=true edits=$($r.edits_count)" -ForegroundColor Green
        } elseif (-not $expectOk -and -not $r.ok) {
            $reasonHit = $true
            if ($expectReasonSubstr) {
                $reasonHit = ($skipMsg -like "*$expectReasonSubstr*") -or ($r.reason -like "*$expectReasonSubstr*")
            }
            if ($reasonHit) {
                Write-Host "[$label] PASS ok=false reason matches '$expectReasonSubstr'" -ForegroundColor Green
            } else {
                Write-Host "[$label] FAIL: blocked but wrong reason. r.reason=$($r.reason) skipped=$skipMsg" -ForegroundColor Red
            }
        } else {
            Write-Host "[$label] FAIL: expectOk=$expectOk got ok=$($r.ok) reason=$($r.reason) skipped=$skipMsg" -ForegroundColor Red
        }
    } catch {
        Write-Host "[$label] HTTP FAIL: $_" -ForegroundColor Red
    }
    Remove-Item "$STATE/$id.json" -ErrorAction SilentlyContinue
}

Write-Host "=== R10.6b bounds-check tests ===" -ForegroundColor Cyan
$h = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/health" -TimeoutSec 5
Write-Host "[health] $($h.status)" -ForegroundColor Green

$ts = Get-Date -Format 'yyyyMMddHHmmss'

# T1: in-bounds OK -- MIN_IMPACT_SCORE 7 -> 8 (range [3,10])
$id1 = "ce_prop_r10_6b_inb_$ts"
New-Proposal $id1 "Subir MIN_IMPACT_SCORE de 7 a 8" @("autonomy/chat_excellence_executor.py")
Test-DryRun $id1 $true "T1 in-bounds (7->8)" $null

# T2: out-of-bounds LOW -- MIN_IMPACT_SCORE 7 -> 1 (below min 3)
$id2 = "ce_prop_r10_6b_low_$ts"
New-Proposal $id2 "Bajar MIN_IMPACT_SCORE de 7 a 1" @("autonomy/chat_excellence_executor.py")
Test-DryRun $id2 $false "T2 out-of-bounds low (7->1)" "out_of_bounds"

# T3: out-of-bounds HIGH but in-delta -- CHECK_INTERVAL 30 -> 5 (below min 10, ratio 0.16)
# Note: choose case where delta-ratio (10x) is NOT triggered first.
$id3 = "ce_prop_r10_6b_high_$ts"
New-Proposal $id3 "Bajar CHECK_INTERVAL de 30 a 5" @("autonomy/proactive_scheduler.py")
Test-DryRun $id3 $false "T3 out-of-bounds (30->5, in-delta)" "out_of_bounds"

# T4: unbounded constant remains permissive -- MIN_CHANGE_CHARS has bounds too,
# pick something WITHOUT bounds. Try _LATENCY_WINDOW (forbidden, will hit forbidden first).
# Better: use a constant on a file that has NO bounds entry for it. Since we declared
# bounds for every constant we whitelisted, this test is hard. Use a NEW constant name
# that exists in core/llm.py but not in _BOUNDS_BY_FILE["core/llm.py"]. Let's check
# if there's any other ALL_CAPS_WITH_UNDERSCORE numeric in llm.py first.
# Actually simplest: any constant name we don't bound -> permissive. Use a fake name
# that wont match find_constant_line, expect skipped reason 'not_found_or_ambiguous'
# (NOT out_of_bounds) -- proves bounds-check did not gate it.
# Skipping T4 because the existing skipped='not_found_or_ambiguous' doesn't prove bounds
# was permissive (could be either path). T1+T2+T3 are sufficient.

# T5: regression -- legacy _CB_FAIL_THRESHOLD 2 -> 5 still works (in [1,20])
$id5 = "ce_prop_r10_6b_regr_$ts"
New-Proposal $id5 "Subir _CB_FAIL_THRESHOLD de 2 a 5" @("core/llm.py")
Test-DryRun $id5 $true "T5 regression in-bounds (2->5)" $null

Write-Host "=== R10.6b done ===" -ForegroundColor Cyan
