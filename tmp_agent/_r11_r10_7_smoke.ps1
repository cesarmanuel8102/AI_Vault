# R10.7 + R11 smoke test - validates new endpoints respond correctly
$ErrorActionPreference = 'Continue'
$base = 'http://127.0.0.1:8090'
$pass = 0
$fail = 0

function Check($name, $cond, $detail) {
    if ($cond) {
        Write-Host "[PASS] $name" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "[FAIL] $name :: $detail" -ForegroundColor Red
        $script:fail++
    }
}

# 1. Health
$h = Invoke-RestMethod -Uri "$base/health" -TimeoutSec 5
Check "brain healthy" ($h.status -eq 'healthy') "status=$($h.status)"

# 2. apply_batch dry-run with 2 fake ids -> should return plans with errors
$body = @{ ids = @('ce_prop_fake_1', 'ce_prop_fake_2'); dry_run = $true } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$base/brain/chat_excellence/proposals/apply_batch" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
Check "apply_batch dry-run responds" ($r.ok -eq $true -and $r.mode -eq 'dry_run') "ok=$($r.ok) mode=$($r.mode)"
Check "apply_batch dry-run has 2 plans" ($r.count -eq 2) "count=$($r.count)"

# 3. apply_batch validates payload (no ids -> 400)
try {
    $r2 = Invoke-RestMethod -Uri "$base/brain/chat_excellence/proposals/apply_batch" -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 5
    Check "apply_batch rejects empty ids" $false "expected 400, got ok=$($r2.ok)"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Check "apply_batch rejects empty ids" ($code -eq 400) "got $code"
}

# 4. R11 evaluate (no proposals with baseline yet -> empty summary)
$ev = Invoke-RestMethod -Uri "$base/brain/chat_excellence/proposals/evaluate" -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 10
Check "evaluate endpoint responds" ($ev.ok -eq $true) "ok=$($ev.ok)"
Check "evaluate summary shape" ($ev.summary.total -ne $null) "summary=$($ev.summary | ConvertTo-Json -Compress)"

# 5. R11 evaluation_status for nonexistent proposal -> 404
try {
    Invoke-RestMethod -Uri "$base/brain/chat_excellence/proposals/ce_prop_nonexistent/evaluation_status" -TimeoutSec 5 | Out-Null
    Check "eval_status 404 for missing" $false "expected 404"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Check "eval_status 404 for missing" ($code -eq 404) "got $code"
}

# 6. Patcher unit: _capture_metric_snapshot returns shape
$py = @"
import sys
sys.path.insert(0, r'C:/AI_VAULT/tmp_agent')
from brain_v9.autonomy.chat_excellence_patcher import _capture_metric_snapshot, _METRIC_BY_CONST, _BOUNDS_BY_FILE
snap = _capture_metric_snapshot('llm_fail_rate')
assert snap is not None, 'snapshot was None'
assert 'value' in snap and 'total' in snap and 'failed' in snap, f'missing keys: {list(snap.keys())}'
assert ('core/llm.py', '_CB_FAIL_THRESHOLD') in _METRIC_BY_CONST, 'mapping missing'
print('snap_value=', round(snap['value'], 4), 'total=', snap['total'], 'failed=', snap['failed'])
print('OK')
"@
$pyOut = $py | python -
Check "metric snapshot works" ($pyOut -match 'OK') "out=$pyOut"

# 7. Patcher unit: bounds warning dedupe (only WARN once per key)
$py2 = @"
import sys, logging
sys.path.insert(0, r'C:/AI_VAULT/tmp_agent')
warns = []
class H(logging.Handler):
    def emit(self, r):
        if r.levelno == logging.WARNING and 'no _BOUNDS_BY_FILE entry' in r.getMessage():
            warns.append(r.getMessage())
from brain_v9.autonomy.chat_excellence_patcher import _check_bounds, _WARNED_NO_BOUNDS
import brain_v9.autonomy.chat_excellence_patcher as p
p.log.addHandler(H())
p.log.setLevel(logging.DEBUG)
_WARNED_NO_BOUNDS.clear()
_check_bounds('SOME_NEW_CONST', 'core/llm.py', 5)
_check_bounds('SOME_NEW_CONST', 'core/llm.py', 7)
_check_bounds('SOME_NEW_CONST', 'core/llm.py', 9)
assert len(warns) == 1, f'expected 1 warn, got {len(warns)}'
print('OK dedupe works')
"@
$pyOut2 = $py2 | python -
Check "bounds warning dedupe" ($pyOut2 -match 'OK dedupe') "out=$pyOut2"

$color = if ($fail -eq 0) { 'Green' } else { 'Red' }
Write-Host "`n=== R10.7 + R11 SMOKE: pass=$pass fail=$fail ===" -ForegroundColor $color
exit $fail
