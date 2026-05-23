# AI_Vault Check Scope Script
# Valida que no se modifiquen archivos prohibidos
# Falla si detecta archivos fuera del scope permitido

param(
    [string[]]$AllowedFiles = @()
)

$ErrorActionPreference = "Stop"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI_VAULT SCOPE CHECK" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$repoRoot = "C:\AI_VAULT"
Set-Location $repoRoot

# Mostrar archivos en diff
Write-Host "[1] ARCHIVOS EN GIT DIFF --NAME-ONLY" -ForegroundColor Yellow
$diffFiles = git diff --name-only
if ($diffFiles) {
    Write-Host $diffFiles
    Write-Host "    Total: $(($diffFiles -split "`n").Count) archivos" -ForegroundColor Cyan
} else {
    Write-Host "    (ningún archivo modificado)" -ForegroundColor Green
}
Write-Host ""

# Verificar archivos prohibidos
Write-Host "[2] VERIFICACION DE ARCHIVOS PROHIBIDOS" -ForegroundColor Yellow

$forbiddenPatterns = @(
    "memory/semantic",
    "^nul$",
    "tmp_agent/strategies",
    "tmp_agent/reports",
    "campaign_gate_",
    "market_cache/.*\.csv"
)

$violations = @()
$allChanges = git diff --name-only

foreach ($pattern in $forbiddenPatterns) {
    $matches = $allChanges | Select-String $pattern
    if ($matches) {
        $violations += $matches
    }
}

# Mostrar resultado
if ($violations.Count -gt 0) {
    Write-Host "ERROR: Se detectaron archivos prohibidos en el diff:" -ForegroundColor Red
    $violations | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "SCOPE CHECK: FAILED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "OK: No se detectaron archivos prohibidos" -ForegroundColor Green
    Write-Host ""
    Write-Host "SCOPE CHECK: PASSED" -ForegroundColor Green
    exit 0
}
