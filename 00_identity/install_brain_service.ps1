# install_brain_service.ps1
# Instala BrainServer como Scheduled Task (ONSTART) corriendo como SYSTEM
# Runner: C:\AI_VAULT\00_identity\run_brain_server.ps1
# Log:    C:\AI_VAULT\00_identity\logs\brain_server.log

$ErrorActionPreference = "Stop"

$TASK = "BrainServer"
$RUN  = "C:\AI_VAULT\00_identity\run_brain_server.ps1"

if (!(Test-Path $RUN)) { throw "No existe el runner: $RUN" }

# Borra si existe
schtasks /Delete /TN $TASK /F 2>$null | Out-Null

# Crea ONSTART como SYSTEM (no requiere contraseña)
$TR = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$RUN`""
schtasks /Create /TN $TASK /SC ONSTART /RL HIGHEST /RU "SYSTEM" /TR $TR /F | Out-Null

# Ejecuta ahora
schtasks /Run /TN $TASK | Out-Null
Start-Sleep -Seconds 2

Write-Host "OK: Task instalada y lanzada => $TASK" -ForegroundColor Green
Write-Host "Runner => $RUN" -ForegroundColor Cyan
Write-Host "Log    => C:\AI_VAULT\00_identity\logs\brain_server.log" -ForegroundColor Cyan
