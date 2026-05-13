$ErrorActionPreference = 'Stop'
$ROOT = 'C:/AI_VAULT/tmp_agent'
$STATE = "$ROOT/state/proposed_patches"
$PORT = 8090
$id = "ce_prop_r10_6_regr_$(Get-Date -Format 'yyyyMMddHHmmss')"

Write-Host "=== R10.6 regression: core/llm.py still patchable ===" -ForegroundColor Cyan

$proposal = [ordered]@{
    proposal_id     = $id
    iter            = 0
    weakness        = "circuit breaker too aggressive"
    proposed_change = "Subir _CB_FAIL_THRESHOLD de 2 a 4"
    affected_files  = @("core/llm.py")
    risk_class      = "low"
    risk_reasons    = @()
    impact_score    = 8
    status          = "pending_review"
    created_at      = (Get-Date).ToString("o")
    source          = "r10_6_regression_test"
}
$json = $proposal | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText("$STATE/$id.json", $json, [System.Text.UTF8Encoding]::new($false))

try {
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/brain/chat_excellence/proposals/$id/dry_run" -Method Post -TimeoutSec 15
  if ($r.ok -and $r.diff -match "_CB_FAIL_THRESHOLD\s*=\s*2" -and $r.diff -match "_CB_FAIL_THRESHOLD\s*=\s*4") {
    Write-Host "[regression] PASS: legacy core/llm.py path intact" -ForegroundColor Green
  } else {
    Write-Host "[regression] FAIL ok=$($r.ok) reason=$($r.reason)" -ForegroundColor Red
    if ($r.diff) { Write-Host $r.diff }
  }
} catch {
  Write-Host "[regression] HTTP FAIL: $_" -ForegroundColor Red
}

Remove-Item "$STATE/$id.json" -ErrorAction SilentlyContinue

# Bonus: forbidden-constant test (should reject MAX_PROPOSALS_KEEP in executor)
$id2 = "ce_prop_r10_6_forbid_$(Get-Date -Format 'yyyyMMddHHmmss')"
$prop2 = [ordered]@{
    proposal_id     = $id2
    iter            = 0
    weakness        = "history grows too big"
    proposed_change = "Bajar MAX_PROPOSALS_KEEP de 200 a 50"
    affected_files  = @("autonomy/chat_excellence_executor.py")
    risk_class      = "low"
    risk_reasons    = @()
    impact_score    = 8
    status          = "pending_review"
    created_at      = (Get-Date).ToString("o")
    source          = "r10_6_forbid_test"
}
$json2 = $prop2 | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText("$STATE/$id2.json", $json2, [System.Text.UTF8Encoding]::new($false))
Start-Sleep -Milliseconds 200
try {
  $r2 = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/brain/chat_excellence/proposals/$id2/dry_run" -Method Post -TimeoutSec 15
  $blocked = ($r2.skipped | Where-Object { $_.constant -eq 'MAX_PROPOSALS_KEEP' -and $_.reason -eq 'forbidden_constant' }).Count -gt 0
  if (-not $r2.ok -and $blocked) {
    Write-Host "[forbidden-test] PASS: MAX_PROPOSALS_KEEP rightly blocked per-file" -ForegroundColor Green
  } else {
    Write-Host "[forbidden-test] FAIL ok=$($r2.ok) reason=$($r2.reason) skipped=$($r2.skipped | ConvertTo-Json -Compress)" -ForegroundColor Red
  }
} catch {
  Write-Host "[forbidden-test] HTTP FAIL: $_" -ForegroundColor Red
}
Remove-Item "$STATE/$id2.json" -ErrorAction SilentlyContinue

Write-Host "=== regression done ===" -ForegroundColor Cyan
