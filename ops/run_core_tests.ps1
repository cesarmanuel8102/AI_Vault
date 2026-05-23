# AI_Vault Core Tests Runner
# Ejecuta los tests mínimos obligatorios

$ErrorActionPreference = "Continue"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI_VAULT CORE TESTS RUNNER" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$repoRoot = "C:\AI_VAULT"
Set-Location $repoRoot

$allPassed = $true

# Test 1: Curated Memory Promotion
Write-Host "[1] TEST: test_curated_memory_promotion.py" -ForegroundColor Yellow
try {
    $result = python -m pytest tests/unit/test_curated_memory_promotion.py -q 2>&1
    $exitCode = $LASTEXITCODE
    
    # Buscar resultado en output
    if ($result -match "passed") {
        $passed = ($result | Select-String "(\d+) passed" | ForEach-Object { $_.Matches.Groups[1].Value })
        Write-Host "    Result: $passed passed" -ForegroundColor Green
    } elseif ($result -match "failed") {
        $failed = ($result | Select-String "(\d+) failed" | ForEach-Object { $_.Matches.Groups[1].Value })
        Write-Host "    Result: $failed failed" -ForegroundColor Red
        $allPassed = $false
    }
    
    if ($exitCode -ne 0) {
        Write-Host "    EXIT CODE: $exitCode" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "    ERROR: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Test 2: Curation Validation Adapter
Write-Host "[2] TEST: test_curation_validation_adapter.py" -ForegroundColor Yellow
try {
    $result = python -m pytest tests/unit/test_curation_validation_adapter.py -q 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($result -match "passed") {
        $passed = ($result | Select-String "(\d+) passed" | ForEach-Object { $_.Matches.Groups[1].Value })
        Write-Host "    Result: $passed passed" -ForegroundColor Green
    } elseif ($result -match "failed") {
        $failed = ($result | Select-String "(\d+) failed" | ForEach-Object { $_.Matches.Groups[1].Value })
        Write-Host "    Result: $failed failed" -ForegroundColor Red
        $allPassed = $false
    }
    
    if ($exitCode -ne 0) {
        Write-Host "    EXIT CODE: $exitCode" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "    ERROR: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Test 3: Smoke Curation Validation Adapter
Write-Host "[3] SMOKE: smoke_curation_validation_adapter.py" -ForegroundColor Yellow
try {
    $result = python tests/smoke/smoke_curation_validation_adapter.py 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($result -match "SMOKE_CURATION_VALIDATION_ADAPTER_OK") {
        Write-Host "    Result: PASSED" -ForegroundColor Green
    } else {
        Write-Host "    Result: FAILED" -ForegroundColor Red
        Write-Host "    Output: $result" -ForegroundColor Red
        $allPassed = $false
    }
    
    if ($exitCode -ne 0) {
        Write-Host "    EXIT CODE: $exitCode" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "    ERROR: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Resumen
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "CORE TESTS SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "ESTADO: TODOS LOS TESTS PASARON" -ForegroundColor Green
    exit 0
} else {
    Write-Host "ESTADO: ALGUNOS TESTS FALLARON" -ForegroundColor Red
    exit 1
}
