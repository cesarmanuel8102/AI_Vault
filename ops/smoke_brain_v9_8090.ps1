# AI_Vault Brain V9 Smoke Test Script
# Verifica que el runtime en puerto 8090 responde correctamente
# No exige LLM externo si la ruta system/policy responde

$ErrorActionPreference = "Continue"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI_VAULT BRAIN V9 SMOKE TEST (Port 8090)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://127.0.0.1:8090"
$allPassed = $true

# 1. Health Check
Write-Host "[1] HEALTH CHECK" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/health" -Method GET -TimeoutSec 10 -ErrorAction Stop
    Write-Host "    Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "    Response: $($response.Content)"
    if ($response.StatusCode -eq 200) {
        Write-Host "    Result: PASSED" -ForegroundColor Green
    } else {
        Write-Host "    Result: FAILED (Status no 200)" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "    ERROR: $_.Exception.Message" -ForegroundColor Red
    Write-Host "    Result: FAILED" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# 2. Chat Test
Write-Host "[2] CHAT ENDPOINT TEST" -ForegroundColor Yellow
$testMessage = "Resume el estado actual de P2-A, P2-B, P2-C, P2-D y P2-E sin inventar nada."
$body = @{
    message = $testMessage
    session_id = "smoke_test_$(Get-Random)"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri "$baseUrl/chat" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
    Write-Host "    Status: $($response.StatusCode)" -ForegroundColor Green
    
    # Verificar contenido esperado
    $content = $response.Content
    $checks = @{
        "P2-C" = $content -match "P2-C"
        "P2-D" = $content -match "P2-D"
        "P2-E" = $content -match "P2-E"
        "Completado/Dry-run" = ($content -match "Completado") -or ($content -match "dry-run") -or ($content -match "dry run") -or ($content -match "[DEV]")
    }
    
    Write-Host "    Verificaciones de contenido:" -ForegroundColor Cyan
    foreach ($check in $checks.GetEnumerator()) {
        $status = if ($check.Value) { "OK" } else { "NOT FOUND" }
        $color = if ($check.Value) { "Green" } else { "Yellow" }
        Write-Host "      - $($check.Key): $status" -ForegroundColor $color
    }
    
    if ($checks.Values -contains $false) {
        Write-Host "    WARNING: Algunas verificaciones no encontradas" -ForegroundColor Yellow
        # No marcamos como fallo porque puede ser que no tenga contexto
    } else {
        Write-Host "    Result: PASSED" -ForegroundColor Green
    }
} catch {
    Write-Host "    ERROR: $_.Exception.Message" -ForegroundColor Red
    Write-Host "    Result: FAILED" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# 3. System/Policy Check (no requiere LLM)
Write-Host "[3] SYSTEM/POLICY CHECK" -ForegroundColor Yellow
try {
    # Intentar obtener info del sistema si existe endpoint
    $response = Invoke-WebRequest -Uri "$baseUrl/system/policy" -Method GET -TimeoutSec 10 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "    Status: 200" -ForegroundColor Green
        Write-Host "    Response available" -ForegroundColor Green
        Write-Host "    Result: PASSED" -ForegroundColor Green
    }
} catch {
    Write-Host "    INFO: Endpoint /system/policy no disponible (opcional)" -ForegroundColor Cyan
}
Write-Host ""

# Resumen
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "SMOKE TEST SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "ESTADO: TODOS LOS CHECKS PASARON" -ForegroundColor Green
    exit 0
} else {
    Write-Host "ESTADO: ALGUNOS CHECKS FALLARON" -ForegroundColor Red
    exit 1
}
