# Actualizar tareas programadas para usar pythonw (sin ventanas)

$ErrorActionPreference = "Continue"

Write-Host "Actualizando tareas programadas para modo silencioso..."

# Eliminar tareas existentes
try {
    Unregister-ScheduledTask -TaskName "AI_VAULT_Services_AutoStart" -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "AI_VAULT_Monitor" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tareas anteriores eliminadas"
} catch {
    Write-Host "No había tareas previas"
}

# Crear nueva tarea silenciosa
$Action = New-ScheduledTaskAction `
    -Execute "C:\AI_VAULT\tmp_agent\start_services.bat" `
    -WorkingDirectory "C:\AI_VAULT\tmp_agent"

$Trigger = New-ScheduledTaskTrigger `
    -AtLogon `
    -User $env:USERNAME `
    -RandomDelay (New-TimeSpan -Seconds 30)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -RunOnlyIfNetworkAvailable:$false

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName "AI_VAULT_AutoStart_Silent" `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "AI_VAULT Services - Inicio silencioso sin ventanas de consola" `
        -ErrorAction Stop
    
    Write-Host "✅ Tarea actualizada exitosamente"
    Write-Host "Los servicios ahora iniciarán en modo silencioso (sin ventanas)"
} catch {
    Write-Host "❌ Error: $_"
    Write-Host ""
    Write-Host "Alternativa manual:"
    Write-Host "1. Copiar start_services.bat al inicio:"
    Write-Host "   copy start_services.bat '%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\\'"
}

Write-Host ""
