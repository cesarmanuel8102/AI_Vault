param(
  [int]$Port = 8010
)
Set-Location -Path $PSScriptRoot

# Start server
Start-Process -WindowStyle Normal powershell -ArgumentList @(
  "-NoProfile","-ExecutionPolicy","Bypass","-Command",
  "python -m uvicorn brain_ui_server:app --host 127.0.0.1 --port $Port"
)

Start-Sleep -Seconds 1
Start-Process "http://127.0.0.1:$Port"
Write-Host "OK: Brain UI arrancando en http://127.0.0.1:$Port" -ForegroundColor Green
