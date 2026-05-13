#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Inicia todos los servicios de Brain V9 con privilegios de Administrador
.DESCRIPTION
    Script PowerShell que inicia Ollama, Dashboard 8070 y Brain V9
    Requiere ejecución como Administrador
#>

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    INICIANDO SERVICIOS BRAIN V9" -ForegroundColor Cyan
Write-Host "    Modo: ADMINISTRADOR" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Función para verificar si un proceso está corriendo
function Test-ProcessRunning($ProcessName) {
    return Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
}

# 1. Iniciar Ollama
Write-Host "[1/3] Iniciando Ollama..." -ForegroundColor Yellow
if (-not (Test-ProcessRunning "ollama")) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
    
    # Verificar
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
        Write-Host "      Ollama OK - $($response.models.Count) modelos" -ForegroundColor Green
    } catch {
        Write-Host "      Esperando Ollama..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
} else {
    Write-Host "      Ollama ya estaba corriendo" -ForegroundColor Green
}

# 2. Iniciar Dashboard 8070
Write-Host "[2/3] Iniciando Dashboard 8070..." -ForegroundColor Yellow
$dashboardPath = "C:\AI_VAULT\00_identity\autonomy_system\simple_dashboard_server.py"
if (Test-Path $dashboardPath) {
    Start-Process -FilePath "python" -ArgumentList $dashboardPath -WindowStyle Hidden -WorkingDirectory "C:\AI_VAULT\00_identity\autonomy_system"
    Start-Sleep -Seconds 3
    
    # Verificar
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8070" -TimeoutSec 3
        Write-Host "      Dashboard OK" -ForegroundColor Green
    } catch {
        Write-Host "      Dashboard iniciando..." -ForegroundColor Yellow
    }
} else {
    Write-Host "      ERROR: No se encontró dashboard_server.py" -ForegroundColor Red
}

# 3. Iniciar Brain V9
Write-Host "[3/3] Iniciando Brain V9..." -ForegroundColor Yellow
$env:PYTHONPATH = "C:\AI_VAULT\tmp_agent"
$env:OLLAMA_MODEL = "llama3.1:8b"
$env:OLLAMA_AGENT_MODEL = "deepseek-r1:14b"

Start-Process -FilePath "python" -ArgumentList "-m brain_v9.main" -WindowStyle Hidden -WorkingDirectory "C:\AI_VAULT\tmp_agent"
Start-Sleep -Seconds 5

# Verificar Brain V9
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8090/health" -TimeoutSec 5
    if ($response.status -eq "healthy") {
        Write-Host "      Brain V9 OK - $($response.sessions) sesiones" -ForegroundColor Green
    }
} catch {
    Write-Host "      Brain V9 iniciando..." -ForegroundColor Yellow
}

# Resumen final
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    SERVICIOS INICIADOS" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Ollama:     http://localhost:11434" -ForegroundColor White
Write-Host "  Dashboard:  http://localhost:8070" -ForegroundColor White
Write-Host "  Brain V9:   http://localhost:8090" -ForegroundColor White
Write-Host ""
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
