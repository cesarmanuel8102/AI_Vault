#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configura Brain V9 para iniciar automáticamente con Windows
.DESCRIPTION
    Crea tareas programadas en el Programador de Tareas de Windows
    para iniciar Ollama, Dashboard y Brain V9 al inicio del sistema
#>

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CONFIGURANDO INICIO AUTOMATICO BRAIN V9" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Nombre de las tareas
$taskNameOllama = "BrainV9_Ollama"
$taskNameDashboard = "BrainV9_Dashboard"
$taskNameBrain = "BrainV9_Main"

# Eliminar tareas existentes si existen
Write-Host "[1/4] Eliminando tareas anteriores..." -ForegroundColor Yellow
Get-ScheduledTask -TaskName "BrainV9_*" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
Write-Host "      OK" -ForegroundColor Green

# 1. Tarea: Ollama
Write-Host "[2/4] Creando tarea Ollama..." -ForegroundColor Yellow
$actionOllama = New-ScheduledTaskAction -Execute "ollama" -Argument "serve"
$triggerOllama = New-ScheduledTaskTrigger -AtStartup
$settingsOllama = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principalOllama = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest

Register-ScheduledTask -TaskName $taskNameOllama -Action $actionOllama -Trigger $triggerOllama -Settings $settingsOllama -Principal $principalOllama -Force | Out-Null
Write-Host "      OK" -ForegroundColor Green

# 2. Tarea: Dashboard (con delay de 10 segundos)
Write-Host "[3/4] Creando tarea Dashboard..." -ForegroundColor Yellow
$actionDashboard = New-ScheduledTaskAction -Execute "python" -Argument "C:\AI_VAULT\00_identity\autonomy_system\simple_dashboard_server.py" -WorkingDirectory "C:\AI_VAULT\00_identity\autonomy_system"
$triggerDashboard = New-ScheduledTaskTrigger -AtStartup
$settingsDashboard = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principalDashboard = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest

Register-ScheduledTask -TaskName $taskNameDashboard -Action $actionDashboard -Trigger $triggerDashboard -Settings $settingsDashboard -Principal $principalDashboard -Force | Out-Null
Write-Host "      OK" -ForegroundColor Green

# 3. Tarea: Brain V9 (con delay de 15 segundos)
Write-Host "[4/4] Creando tarea Brain V9..." -ForegroundColor Yellow
$actionBrain = New-ScheduledTaskAction -Execute "python" -Argument "-m brain_v9.main" -WorkingDirectory "C:\AI_VAULT\tmp_agent"
$triggerBrain = New-ScheduledTaskTrigger -AtStartup
$settingsBrain = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principalBrain = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest

# Agregar variables de entorno
$envVars = @{
    "PYTHONPATH" = "C:\AI_VAULT\tmp_agent"
    "OLLAMA_MODEL" = "llama3.1:8b"
    "OLLAMA_AGENT_MODEL" = "deepseek-r1:14b"
}

Register-ScheduledTask -TaskName $taskNameBrain -Action $actionBrain -Trigger $triggerBrain -Settings $settingsBrain -Principal $principalBrain -Force | Out-Null
Write-Host "      OK" -ForegroundColor Green

# Resumen
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    CONFIGURACIÓN COMPLETADA" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tareas creadas:" -ForegroundColor White
Write-Host "  1. BrainV9_Ollama      - Inicia al arrancar Windows" -ForegroundColor Gray
Write-Host "  2. BrainV9_Dashboard   - Inicia al arrancar Windows" -ForegroundColor Gray
Write-Host "  3. BrainV9_Main        - Inicia al arrancar Windows" -ForegroundColor Gray
Write-Host ""
Write-Host "Para ver las tareas: Programador de Tareas" -ForegroundColor Yellow
Write-Host "Para iniciar manualmente: INICIAR_ADMIN.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "Presiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
