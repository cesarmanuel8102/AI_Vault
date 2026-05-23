# AI_Vault Migration Preflight Script
# Verifica el estado del repo antes de cualquier migración
# NO modifica nada - solo reporta

$ErrorActionPreference = "Continue"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI_VAULT MIGRATION PREFLIGHT CHECK" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$repoRoot = "C:\AI_VAULT"
Set-Location $repoRoot

# 1. Branch actual
Write-Host "[1] BRANCH ACTUAL" -ForegroundColor Yellow
$branch = git branch --show-current
Write-Host "    Branch: $branch"
Write-Host ""

# 2. Git status
Write-Host "[2] GIT STATUS --SHORT" -ForegroundColor Yellow
$status = git status --short
if ($status) {
    Write-Host $status
} else {
    Write-Host "    (limpio)" -ForegroundColor Green
}
Write-Host ""

# 3. Últimos 5 commits
Write-Host "[3] ULTIMOS 5 COMMITS" -ForegroundColor Yellow
git log --oneline -5
Write-Host ""

# 4. Commits locales pendientes
Write-Host "[4] COMMITS LOCALES PENDIENTES vs origin/codex/own-capital-sustainable-return" -ForegroundColor Yellow
$pending = git log --oneline origin/codex/own-capital-sustainable-return..HEAD 2>$null
if ($pending) {
    Write-Host $pending -ForegroundColor Yellow
} else {
    Write-Host "    (ninguno)" -ForegroundColor Green
}
Write-Host ""

# 5. Python version
Write-Host "[5] PYTHON VERSION" -ForegroundColor Yellow
python --version
Write-Host ""

# 6. Pytest check
Write-Host "[6] PYTEST CHECK" -ForegroundColor Yellow
try {
    $pytestVersion = python -m pytest --version 2>&1 | Select-String "pytest"
    if ($pytestVersion) {
        Write-Host "    OK: $pytestVersion" -ForegroundColor Green
    } else {
        Write-Host "    WARNING: pytest no encontrado" -ForegroundColor Yellow
    }
} catch {
    Write-Host "    WARNING: pytest no disponible" -ForegroundColor Yellow
}
Write-Host ""

# 7. Puerto 8090
Write-Host "[7] PUERTO 8090 CHECK" -ForegroundColor Yellow
$tcpConnection = Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue
if ($tcpConnection) {
    Write-Host "    OK: Puerto 8090 está activo" -ForegroundColor Green
    Write-Host "    PID: $($tcpConnection.OwningProcess)"
    try {
        $process = Get-Process -Id $tcpConnection.OwningProcess -ErrorAction SilentlyContinue
        Write-Host "    Proceso: $($process.ProcessName)"
    } catch {
        Write-Host "    No se pudo obtener nombre del proceso"
    }
} else {
    Write-Host "    INFO: Puerto 8090 no está activo" -ForegroundColor Cyan
}
Write-Host ""

# 8. Health check si está activo
Write-Host "[8] HEALTH CHECK (8090)" -ForegroundColor Yellow
if ($tcpConnection) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8090/health" -Method GET -TimeoutSec 5 -ErrorAction Stop
        Write-Host "    Status: $($response.StatusCode)" -ForegroundColor Green
        Write-Host "    Response: $($response.Content)"
    } catch {
        Write-Host "    ERROR: No se pudo conectar a /health" -ForegroundColor Red
    }
} else {
    Write-Host "    SKIP: Puerto 8090 no activo"
}
Write-Host ""

# 9. Archivos prohibidos sucios
Write-Host "[9] ARCHIVOS PROHIBIDOS MODIFICADOS/UNTRACKED" -ForegroundColor Yellow
Write-Host "    Verificando archivos prohibidos..." -ForegroundColor Cyan

$prohibitedFound = $false

# memory/semantic
$semanticFiles = git status --short | Select-String "memory/semantic"
if ($semanticFiles) {
    Write-Host "    WARNING: memory/semantic/* modificado:" -ForegroundColor Red
    $semanticFiles | ForEach-Object { Write-Host "      $_" -ForegroundColor Red }
    $prohibitedFound = $true
}

# nul
$nulFiles = git status --short | Select-String "^\\?\\? nul" -ErrorAction SilentlyContinue
if ($nulFiles) {
    Write-Host "    WARNING: archivo 'nul' detectado (untracked)" -ForegroundColor Red
    $prohibitedFound = $true
}

# tmp_agent/strategies
$strategiesFiles = git status --short | Select-String "tmp_agent/strategies"
if ($strategiesFiles) {
    Write-Host "    WARNING: tmp_agent/strategies/* modificado:" -ForegroundColor Yellow
    $strategiesFiles | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
}

# tmp_agent/reports
$reportsFiles = git status --short | Select-String "tmp_agent/reports"
if ($reportsFiles) {
    Write-Host "    WARNING: tmp_agent/reports/* modificado:" -ForegroundColor Yellow
    $reportsFiles | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
}

if (-not $prohibitedFound) {
    Write-Host "    OK: No hay archivos prohibidos críticos modificados" -ForegroundColor Green
}
Write-Host ""

# 10. Resumen
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "RESUMEN PREFLIGHT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Branch: $branch"
Write-Host "Commit base: $(git rev-parse --short HEAD)"
if ($prohibitedFound) {
    Write-Host "ESTADO: HAY ARCHIVOS PROHIBIDOS MODIFICADOS" -ForegroundColor Red
    Write-Host "ACCION: NO proceder con commit hasta resolver" -ForegroundColor Red
} elseif ($status) {
    Write-Host "ESTADO: Working tree con cambios" -ForegroundColor Yellow
    Write-Host "ACCION: Revisar scope antes de proceder"
} else {
    Write-Host "ESTADO: OK para proceder" -ForegroundColor Green
}
Write-Host "============================================================" -ForegroundColor Cyan
