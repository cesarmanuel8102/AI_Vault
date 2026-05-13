#Requires -RunAsAdministrator
# Crea servicios de Windows para Brain V9 (más robusto que tareas programadas)

Write-Host "CREANDO SERVICIOS WINDOWS PARA BRAIN V9" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Instalar NSSM (Non-Sucking Service Manager) si no existe
$nssmPath = "C:\AI_VAULT\tmp_agent\nssm.exe"
if (-not (Test-Path $nssmPath)) {
    Write-Host "Descargando NSSM..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$env:TEMP\nssm.zip"
    Expand-Archive -Path "$env:TEMP\nssm.zip" -DestinationPath "$env:TEMP\nssm" -Force
    Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" $nssmPath -Force
}

# Crear servicio Ollama
Write-Host "[1/3] Creando servicio Ollama..." -ForegroundColor Yellow
& $nssmPath install BrainV9_Ollama "ollama" "serve"
& $nssmPath set BrainV9_Ollama DisplayName "Brain V9 - Ollama"
& $nssmPath set BrainV9_Ollama Start SERVICE_AUTO_START
net start BrainV9_Ollama 2>$null
Write-Host "      OK" -ForegroundColor Green

# Crear servicio Dashboard
Write-Host "[2/3] Creando servicio Dashboard..." -ForegroundColor Yellow
& $nssmPath install BrainV9_Dashboard "python" "simple_dashboard_server.py"
& $nssmPath set BrainV9_Dashboard DisplayName "Brain V9 - Dashboard"
& $nssmPath set BrainV9_Dashboard AppDirectory "C:\AI_VAULT\00_identity\autonomy_system"
& $nssmPath set BrainV9_Dashboard Start SERVICE_AUTO_START
net start BrainV9_Dashboard 2>$null
Write-Host "      OK" -ForegroundColor Green

# Crear servicio Brain V9
Write-Host "[3/3] Creando servicio Brain V9..." -ForegroundColor Yellow
& $nssmPath install BrainV9_Main "python" "-m brain_v9.main"
& $nssmPath set BrainV9_Main DisplayName "Brain V9 - Core"
& $nssmPath set BrainV9_Main AppDirectory "C:\AI_VAULT\tmp_agent"
& $nssmPath set BrainV9_Main AppEnvironmentExtra "PYTHONPATH=C:\AI_VAULT\tmp_agent"
& $nssmPath set BrainV9_Main Start SERVICE_AUTO_START
net start BrainV9_Main 2>$null
Write-Host "      OK" -ForegroundColor Green

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "SERVICIOS CREADOS - INICIO AUTOMATICO" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Servicios instalados:" -ForegroundColor White
Write-Host "  - BrainV9_Ollama     (inicio automatico)" -ForegroundColor Gray
Write-Host "  - BrainV9_Dashboard  (inicio automatico)" -ForegroundColor Gray
Write-Host "  - BrainV9_Main       (inicio automatico)" -ForegroundColor Gray
Write-Host ""
Write-Host "Para gestionar: services.msc" -ForegroundColor Yellow
Write-Host ""
Pause
