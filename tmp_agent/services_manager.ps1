# AI_VAULT Services Manager
# Script de PowerShell para gestionar servicios de Brain V9 y Dashboard
# Incluye: inicio, parada, monitoreo y auto-recuperación

param(
    [Parameter()]
    [ValidateSet("start", "stop", "restart", "status", "monitor", "install")]
    [string]$Action = "status",
    
    [Parameter()]
    [switch]$AutoRecover
)

# Configuración
$Services = @{
    "BrainV9" = @{
        "Name" = "Brain V9"
        "Port" = 8090
        "Path" = "C:\AI_VAULT\tmp_agent"
        "Command" = "pythonw -m brain_v9.main"
        "LogPath" = "C:\AI_VAULT\tmp_agent\logs\brain_v9_service.log"
        "HealthEndpoint" = "http://127.0.0.1:8090/health"
    }
    "Dashboard" = @{
        "Name" = "Dashboard"
        "Port" = 8070
        "Path" = "C:\AI_VAULT\00_identity\autonomy_system"
        "Command" = "python dashboard_server.py"
        "LogPath" = "C:\AI_VAULT\00_identity\autonomy_system\dashboard_service.log"
        "HealthEndpoint" = "http://127.0.0.1:8070/api/health"
    }
}

$LogFile = "C:\AI_VAULT\tmp_agent\service_manager.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $LogFile -Value $logEntry
    Write-Host $logEntry
}

function Test-ServiceHealth {
    param([hashtable]$Service)
    try {
        $response = Invoke-RestMethod -Uri $Service.HealthEndpoint -Method GET -TimeoutSec 5 -ErrorAction Stop
        return $response.status -eq "healthy" -or $response.ok -eq $true
    }
    catch {
        return $false
    }
}

function Get-ServiceStatus {
    param([hashtable]$Service)
    $process = Get-Process | Where-Object { $_.ProcessName -like "*python*" -and $_.CommandLine -like "*$($Service.Command)*" } | Select-Object -First 1
    $isHealthy = Test-ServiceHealth -Service $Service
    
    return @{
        "Running" = $null -ne $process
        "Healthy" = $isHealthy
        "ProcessId" = if ($process) { $process.Id } else { $null }
    }
}

function Start-ServiceWrapper {
    param([hashtable]$Service)
    $status = Get-ServiceStatus -Service $Service
    
    if ($status.Running) {
        Write-Log "$($Service.Name) ya está corriendo (PID: $($status.ProcessId))"
        return
    }
    
    Write-Log "Iniciando $($Service.Name)..."
    
    # Limpiar logs antiguos
    if (Test-Path $Service.LogPath) {
        $logSize = (Get-Item $Service.LogPath).Length / 1MB
        if ($logSize -gt 10) {
            Move-Item $Service.LogPath "$($Service.LogPath).old" -Force
            Write-Log "Rotado log de $($Service.Name)"
        }
    }
    
    # Iniciar proceso en background
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = $Service.Command.Replace("python ", "")
    $psi.WorkingDirectory = $Service.Path
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    
    $process = [System.Diagnostics.Process]::Start($psi)
    
    # Esperar y verificar
    Start-Sleep -Seconds 5
    $newStatus = Get-ServiceStatus -Service $Service
    
    if ($newStatus.Healthy) {
        Write-Log "$($Service.Name) iniciado exitosamente (PID: $($newStatus.ProcessId))" "SUCCESS"
    }
    else {
        Write-Log "ADVERTENCIA: $($Service.Name) no responde correctamente" "WARN"
    }
}

function Stop-ServiceWrapper {
    param([hashtable]$Service)
    $processes = Get-Process | Where-Object { $_.ProcessName -like "*python*" -and $_.CommandLine -like "*$($Service.Command)*" }
    
    foreach ($proc in $processes) {
        Write-Log "Deteniendo $($Service.Name) (PID: $($proc.Id))..."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    
    # Matar también por puerto
    $port = $Service.Port
    $netstat = netstat -ano | Select-String ":$port"
    foreach ($line in $netstat) {
        if ($line -match "\s+(\d+)\s*$") {
            $pid = $matches[1]
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Log "Liberado proceso en puerto $port (PID: $pid)"
        }
    }
    
    Write-Log "$($Service.Name) detenido"
}

function Monitor-Services {
    Write-Log "Iniciando monitoreo continuo de servicios..."
    
    while ($true) {
        foreach ($serviceName in $Services.Keys) {
            $service = $Services[$serviceName]
            $status = Get-ServiceStatus -Service $service
            
            if (-not $status.Healthy) {
                Write-Log "⚠️ $($service.Name) no responde. Reiniciando..." "WARN"
                Stop-ServiceWrapper -Service $service
                Start-Sleep -Seconds 2
                Start-ServiceWrapper -Service $service
            }
        }
        
        Start-Sleep -Seconds 30
    }
}

function Install-AutoStart {
    Write-Log "Instalando tarea de inicio automático..."
    
    $taskName = "AI_VAULT_Services_AutoStart"
    $scriptPath = $PSCommandPath
    
    # Crear acción
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$scriptPath`" -Action start"
    
    # Crear trigger (al inicio con delay de 30 segundos)
    $trigger = New-ScheduledTaskTrigger -AtLogon -RandomDelay (New-TimeSpan -Seconds 30)
    
    # Crear settings
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    
    # Crear tarea
    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force
        Write-Log "Tarea programada '$taskName' instalada exitosamente" "SUCCESS"
    }
    catch {
        Write-Log "Error instalando tarea: $_" "ERROR"
    }
}

# Ejecución principal
switch ($Action) {
    "start" {
        Write-Log "=== INICIANDO SERVICIOS AI_VAULT ==="
        foreach ($serviceName in $Services.Keys) {
            Start-ServiceWrapper -Service $Services[$serviceName]
        }
        
        if ($AutoRecover) {
            Monitor-Services
        }
    }
    
    "stop" {
        Write-Log "=== DETENIENDO SERVICIOS AI_VAULT ==="
        foreach ($serviceName in $Services.Keys) {
            Stop-ServiceWrapper -Service $Services[$serviceName]
        }
    }
    
    "restart" {
        & $PSCommandPath -Action stop
        Start-Sleep -Seconds 3
        & $PSCommandPath -Action start -AutoRecover:$AutoRecover
    }
    
    "status" {
        Write-Log "=== ESTADO DE SERVICIOS ==="
        foreach ($serviceName in $Services.Keys) {
            $service = $Services[$serviceName]
            $status = Get-ServiceStatus -Service $service
            $healthIcon = if ($status.Healthy) { "✓" } else { "✗" }
            $statusText = if ($status.Running) { "RUNNING" } else { "STOPPED" }
            Write-Log "$healthIcon $($service.Name) [$statusText] - Puerto: $($service.Port)" $(if ($status.Healthy) { "SUCCESS" } else { "WARN" })
        }
    }
    
    "monitor" {
        Monitor-Services
    }
    
    "install" {
        Install-AutoStart
    }
}

Write-Log "=== SERVICES MANAGER COMPLETADO ==="
