param(
  [string]$HostAddr = "127.0.0.1",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

# Nunca uses $pid (PowerShell lo trata como $PID). Usa nombres explícitos.
function Get-ListenerPid([int]$p){
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($null -eq $c){ return $null }
  return $c.OwningProcess
}

function Describe-Proc([int]$p){
  Get-CimInstance Win32_Process -Filter "ProcessId=$p" |
    Select-Object ProcessId,Name,CommandLine |
    Format-List | Out-String
}

function Wait-Port-Free([int]$p, [int]$ms=10000){
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while($sw.ElapsedMilliseconds -lt $ms){
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if(-not $c){ return $true }
    Start-Sleep -Milliseconds 200
  }
  return $false
}

# Ensure we are in runtime dir
Set-Location "C:\AI_VAULT\00_identity"

Write-Host "== Brain Lab Hardened Launcher =="
Write-Host "Runtime: C:\AI_VAULT\00_identity"
Write-Host "Target: http://$HostAddr`:$Port"

# Kill current listener if exists
$listenerPid = Get-ListenerPid $Port
if($listenerPid){
  Write-Host "Port $Port LISTENING by PID $listenerPid"
  Write-Host (Describe-Proc $listenerPid)

  try {
    Stop-Process -Id $listenerPid -Force -ErrorAction Stop
    Write-Host "Killed PID $listenerPid"
  } catch {
    Write-Host "WARNING: failed to kill PID $listenerPid"
    throw
  }

  if(-not (Wait-Port-Free $Port 12000)){
    throw "Port $Port did not free within timeout"
  }
  Write-Host "Port $Port freed"
} else {
  Write-Host "Port $Port is free"
}

# Start uvicorn (foreground)
Write-Host "Starting: python -m uvicorn brain_server:app --host $HostAddr --port $Port"
python -m uvicorn brain_server:app --host $HostAddr --port $Port
