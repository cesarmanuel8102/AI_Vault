Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "AI LOCAL STRATEGIC DIAGNOSTIC REPORT"
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host ">> SISTEMA OPERATIVO" -ForegroundColor Yellow
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion
Write-Host ""

Write-Host ">> CPU / RAM" -ForegroundColor Yellow
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, MaxClockSpeed
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
Write-Host ""

Write-Host ">> GPU NVIDIA" -ForegroundColor Yellow
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi
} else {
    Write-Host "NVIDIA-SMI NO DETECTADO" -ForegroundColor Red
}
Write-Host ""

Write-Host ">> POWER PLAN" -ForegroundColor Yellow
powercfg /GETACTIVESCHEME
Write-Host ""

Write-Host ">> PYTHON" -ForegroundColor Yellow
python --version
py -V
Write-Host ""

Write-Host ">> OLLAMA STATUS" -ForegroundColor Yellow
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    ollama list
} else {
    Write-Host "Ollama NO instalado" -ForegroundColor Red
}
Write-Host ""

Write-Host ">> OPEN WEBUI (PUERTO 3000)" -ForegroundColor Yellow
try {
    (Invoke-WebRequest -UseBasicParsing http://localhost:3000).StatusCode
} catch {
    Write-Host "Open WebUI NO responde" -ForegroundColor Red
}
Write-Host ""

Write-Host ">> BRAIN DATABASE" -ForegroundColor Yellow
if (Test-Path "C:\AI_VAULT\00_identity\brain.db") {
    Write-Host "brain.db EXISTE" -ForegroundColor Green
} else {
    Write-Host "brain.db NO encontrado" -ForegroundColor Red
}
Write-Host ""

Write-Host ">> ROUTER" -ForegroundColor Yellow
if (Test-Path "C:\AI_VAULT\00_identity\brain_router.py") {
    Write-Host "brain_router.py EXISTE" -ForegroundColor Green
} else {
    Write-Host "brain_router.py NO encontrado" -ForegroundColor Red
}
Write-Host ""

Write-Host "============================================="
Write-Host "FIN DEL DIAGNÓSTICO"
Write-Host "============================================="
Write-Host ""
