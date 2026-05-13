$ErrorActionPreference = 'Continue'
Write-Host "=== R10.5b smoke test ===" -ForegroundColor Cyan

# 1) brain healthy?
try {
  $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/health' -TimeoutSec 5
  Write-Host "[health] OK status=$($h.status)" -ForegroundColor Green
} catch {
  Write-Host "[health] FAIL: $_" -ForegroundColor Red
  exit 1
}

# 2) dashboard.html served and contains new strings
try {
  $html = Invoke-WebRequest -Uri 'http://127.0.0.1:8090/dashboard' -TimeoutSec 5 -UseBasicParsing
  $body = $html.Content
  $checks = @(
    'ce-modal',
    'ceDryRun',
    'ceApplyReal',
    'ceRollback',
    'ceShowGateLog',
    'applied_pending_health',
    'rolled_back_auto',
    '_ceColorDiff',
    '_ceScheduleFastPoll'
  )
  $missing = @()
  foreach ($c in $checks) {
    if ($body -notmatch [regex]::Escape($c)) { $missing += $c }
  }
  if ($missing.Count -eq 0) {
    Write-Host "[html] all 9 R10.5b markers present" -ForegroundColor Green
  } else {
    Write-Host "[html] MISSING markers: $($missing -join ', ')" -ForegroundColor Red
  }
} catch {
  Write-Host "[html] FAIL: $_" -ForegroundColor Red
}

# 3) endpoints reachable (use rolled_back_auto proposal from prior test)
$pid_known = 'ce_prop_20260504_133441'
try {
  $log = Invoke-RestMethod -Uri "http://127.0.0.1:8090/brain/chat_excellence/proposals/$pid_known/health_gate_log?tail=5" -TimeoutSec 5
  Write-Host "[gate_log] OK lines_total=$($log.lines_total) log_exists=$($log.log_exists)" -ForegroundColor Green
} catch {
  Write-Host "[gate_log] FAIL: $_" -ForegroundColor Yellow
}

try {
  $list = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/chat_excellence/proposals?limit=5' -TimeoutSec 5
  Write-Host "[proposals] OK total=$($list.stats.total)" -ForegroundColor Green
  $statusList = $list.items | ForEach-Object { $_.status } | Sort-Object -Unique
  Write-Host "  statuses present: $($statusList -join ', ')"
} catch {
  Write-Host "[proposals] FAIL: $_" -ForegroundColor Red
}

Write-Host "=== smoke test done ===" -ForegroundColor Cyan
