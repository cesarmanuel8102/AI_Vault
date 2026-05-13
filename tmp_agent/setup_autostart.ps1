# AI_VAULT Services Auto-Start Setup
# Crear tarea programada para iniciar servicios automaticamente

$ErrorActionPreference = "Continue"

# Verificar si somos admin
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "⚠️  Ejecutando como usuario normal..." -ForegroundColor Yellow
    Write-Host "Intentando crear tarea sin privilegios elevados..." -ForegroundColor Yellow
}

# Configuracion
$TaskName = "AI_VAULT_Services_AutoStart"
$ScriptPath = "C:\AI_VAULT\tmp_agent\services_manager.ps1"
$ActionArg = "-Action start -AutoRecover"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI_VAULT SERVICES AUTO-START SETUP" -ForegroundColor Cyan
Write-Host "========================================"
Write-Host ""

# Verificar si el script existe
if (-not (Test-Path $ScriptPath)) {
    Write-Host "❌ ERROR: No se encuentra $ScriptPath" -ForegroundColor Red
    exit 1
}

# Eliminar tarea existente si existe
try {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "[INFO] Eliminando tarea existente..."
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
} catch {
    # No existe, continuar
}

# Crear accion
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`" $ActionArg"

# Crear trigger (al inicio de sesion con delay)
$Trigger = New-ScheduledTaskTrigger `
    -AtLogon `
    -User $env:USERNAME `
    -RandomDelay (New-TimeSpan -Seconds 30)

# Crear settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -Priority 4

# Crear tarea
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "AI_VAULT Services Auto-Start - Inicia Brain V9 y Dashboard automaticamente" `
        -ErrorAction Stop
    
    Write-Host ""
    Write-Host "✅ INSTALACION COMPLETADA" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Servicios se iniciaran automaticamente:" -ForegroundColor White
    Write-Host "  • 30 segundos despues de iniciar sesion" -ForegroundColor Gray
    Write-Host "  • Con auto-recuperacion activa" -ForegroundColor Gray
    Write-Host "  • Monitoreo cada 30 segundos" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Comandos utiles:" -ForegroundColor Yellow
    Write-Host "  Verificar: Get-ScheduledTask -TaskName $TaskName" -ForegroundColor DarkGray
    Write-Host "  Ejecutar ahora: Start-ScheduledTask -TaskName $TaskName" -ForegroundColor DarkGray
    Write-Host "  Desinstalar: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false" -ForegroundColor DarkGray
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "❌ ERROR al crear tarea: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Intentando metodo alternativo..." -ForegroundColor Yellow
    
    # Metodo alternativo con schtasks
    $schtasksCmd = "schtasks /Create /F /TN `"$TaskName`" /TR `"powershell.exe -ExecutionPolicy Bypass -File `"`"$ScriptPath`"`" $ActionArg`" /SC ONLOGON /DELAY 0000:30"
    Write-Host "Ejecutando: $schtasksCmd" -ForegroundColor DarkGray
    
    try {
        Invoke-Expression $schtasksCmd
        Write-Host "✅ Tarea creada con schtasks" -ForegroundColor Green
    } catch {
        Write-Host "❌ Fallo metodo alternativo: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "Para instalar manualmente:" -ForegroundColor Yellow
        Write-Host "1. Abre Task Scheduler (taskschd.msc)" -ForegroundColor White
        Write-Host "2. Crea tarea nueva llamada '$TaskName'" -ForegroundColor White
        Write-Host "3. Trigger: Al iniciar sesion (con 30 seg delay)" -ForegroundColor White
        Write-Host "4. Action: powershell.exe -ExecutionPolicy Bypass -File `"$ScriptPath`" $ActionArg" -ForegroundColor White
    }
}

Write-Host ""
