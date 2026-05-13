# AI_VAULT Services - Inicio Silencioso (Sin ventanas)
$ErrorActionPreference = "Continue"

# Función para matar procesos existentes
function Kill-ExistingProcess {
    param([string]$Pattern)
    Get-Process python*, pythonw* -ErrorAction SilentlyContinue | Where-Object { 
        $_.CommandLine -like "*$Pattern*" -or $_.Path -like "*$Pattern*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
}

# Matar procesos previos
Kill-ExistingPattern "brain_v9.main"
Kill-ExistingPattern "dashboard_server.py"
Start-Sleep -Seconds 2

# Iniciar Brain V9 sin ventana
$brainV9 = Start-Process -FilePath "pythonw.exe" `
    -ArgumentList "-m brain_v9.main" `
    -WorkingDirectory "C:\AI_VAULT\tmp_agent" `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Brain V9 iniciado (PID: $($brainV9.Id))"

# Esperar que inicie
Start-Sleep -Seconds 5

# Iniciar Dashboard sin ventana
$dashboard = Start-Process -FilePath "pythonw.exe" `
    -ArgumentList "dashboard_server.py" `
    -WorkingDirectory "C:\AI_VAULT\00_identity\autonomy_system" `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Dashboard iniciado (PID: $($dashboard.Id))"

Write-Host "Servicios iniciados en modo silencioso"
