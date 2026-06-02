# =============================================================================
# Phase 1 - Local Validation Runner (read-only)
# Runs py_compile on critical modules + the 3 Phase 0 unit tests + import smoke.
# Does NOT modify any files. Exits non-zero if anything fails.
# Run from repo root: powershell -ExecutionPolicy Bypass -File tmp_agent/brain_v9/ops/phase1_local_validation.ps1
# =============================================================================

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $repoRoot

Write-Host "[phase1] repo_root = $repoRoot" -ForegroundColor Cyan

$failures = @()

function Step($label, $scriptblock) {
    Write-Host ""
    Write-Host "==> $label" -ForegroundColor Cyan
    try {
        & $scriptblock
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
            $script:failures += $label
            Write-Host "FAIL: $label (exit=$LASTEXITCODE)" -ForegroundColor Red
        } else {
            Write-Host "OK:   $label" -ForegroundColor Green
        }
    } catch {
        $script:failures += $label
        Write-Host "FAIL: $label - $($_.Exception.Message)" -ForegroundColor Red
    }
}

# 1. py_compile critical modules ----------------------------------------------
$compileTargets = @(
    'tmp_agent/brain_v9/main.py',
    'tmp_agent/brain_v9/config.py',
    'tmp_agent/brain_v9/governance/execution_gate.py',
    'tmp_agent/brain_v9/api_security.py',
    'tmp_agent/brain_v9/core/session.py'
)
foreach ($t in $compileTargets) {
    Step "py_compile $t" { python -m py_compile $t }
}

# 2. Phase 0 unit tests (run as scripts, no pytest required) -------------------
$phase0Tests = @(
    'tests/unit/test_execution_gate_god_p3.py',
    'tests/unit/test_dev_endpoints_default_off.py',
    'tests/unit/test_selfdev_protected_paths.py'
)
foreach ($t in $phase0Tests) {
    Step "run $t" { python $t }
}

# 3. Import smoke --------------------------------------------------------------
Step 'import smoke (execution_gate + config)' {
    python -c "import sys; sys.path.insert(0, 'tmp_agent'); from brain_v9.governance.execution_gate import ExecutionGate; from brain_v9.config import BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS; print('PHASE1_IMPORT_SMOKE_OK')"
}

# Summary ----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($failures.Count -eq 0) {
    Write-Host "PHASE1_LOCAL_VALIDATION: ALL PASS" -ForegroundColor Green
    exit 0
} else {
    Write-Host "PHASE1_LOCAL_VALIDATION: FAILED" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
