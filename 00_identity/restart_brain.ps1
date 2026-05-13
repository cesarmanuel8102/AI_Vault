$ErrorActionPreference="Stop"

# CONFIG
$Port = 8010
$Root = "C:\AI_VAULT\00_identity"
$App  = "brain_server:app"

$py = (Get-Command python).Source

# Stop listener on port
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if($listener){
  $listenerPid = $listener.OwningProcess
  Write-Host "Stopping PID $listenerPid on port $Port..."
  Stop-Process -Id $listenerPid -Force
  Start-Sleep -Milliseconds 600
} else {
  Write-Host "No listener on port $Port."
}

# Start uvicorn in a NEW PS7 window (persistent)
$cmd = "cd `"$Root`"; `"$py`" -m uvicorn $App --host 127.0.0.1 --port $Port --log-level info"
Start-Process -FilePath "pwsh.exe" -ArgumentList @("-NoExit","-NoProfile","-ExecutionPolicy","Bypass","-Command",$cmd)

Write-Host "Started. Verify with:"
Write-Host "  Invoke-RestMethod http://127.0.0.1:$Port/v1/agent/healthz"
