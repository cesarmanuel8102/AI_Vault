$ErrorActionPreference = 'Stop'
$ROOT = 'C:/AI_VAULT/tmp_agent'
$STATE = "$ROOT/state/proposed_patches"
$PORT = 8090
$id = "ce_prop_r10_6_test_$(Get-Date -Format 'yyyyMMddHHmmss')"

Write-Host "=== R10.6 e2e: dry-run on new whitelist file ===" -ForegroundColor Cyan
Write-Host "proposal_id = $id"

try {
  $h = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/health" -TimeoutSec 5
  Write-Host "[health] OK status=$($h.status)" -ForegroundColor Green
} catch {
  Write-Host "[health] FAIL - brain not running" -ForegroundColor Red
  exit 1
}

# Create synthetic proposal JSON directly on disk
$proposal = [ordered]@{
    proposal_id     = $id
    iter            = 0
    weakness        = "executor accepts low-quality proposals"
    proposed_change = "Subir MIN_IMPACT_SCORE de 7 a 8 para reducir ruido"
    affected_files  = @("autonomy/chat_excellence_executor.py")
    risk_class      = "low"
    risk_reasons    = @()
    impact_score    = 8
    status          = "pending_review"
    created_at      = (Get-Date).ToString("o")
    source          = "r10_6_synthetic_test"
}
$json = $proposal | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText("$STATE/$id.json", $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "[setup] synthetic proposal written" -ForegroundColor Green

# Dry-run via endpoint
try {
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/brain/chat_excellence/proposals/$id/dry_run" -Method Post -TimeoutSec 15
  if ($r.ok) {
    Write-Host "[dry_run] OK edits_count=$($r.edits_count)" -ForegroundColor Green
    Write-Host "--- diff preview ---" -ForegroundColor DarkGray
    Write-Host $r.diff
    Write-Host "--- end diff ---" -ForegroundColor DarkGray
    if ($r.diff -match "MIN_IMPACT_SCORE\s*=\s*7" -and $r.diff -match "MIN_IMPACT_SCORE\s*=\s*8") {
      Write-Host "[diff-content] PASS: contains both old(7) and new(8) values" -ForegroundColor Green
    } else {
      Write-Host "[diff-content] FAIL: expected MIN_IMPACT_SCORE 7->8 not seen" -ForegroundColor Yellow
    }
  } else {
    Write-Host "[dry_run] rejected: reason=$($r.reason)" -ForegroundColor Yellow
    if ($r.skipped) { Write-Host "  skipped: $($r.skipped | ConvertTo-Json -Compress)" }
    Write-Host "  HINT: if reason='no_constant_changes_extracted' the brain still has OLD patcher cached. Restart brain to load R10.6." -ForegroundColor Yellow
  }
} catch {
  Write-Host "[dry_run] HTTP FAIL: $_" -ForegroundColor Red
}

# Cleanup
Remove-Item "$STATE/$id.json" -ErrorAction SilentlyContinue
Write-Host "[cleanup] synthetic proposal deleted" -ForegroundColor DarkGray
Write-Host "=== R10.6 e2e done ===" -ForegroundColor Cyan
