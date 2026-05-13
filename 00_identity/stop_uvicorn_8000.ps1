$ErrorActionPreference = "SilentlyContinue"

$logs    = "C:\AI_VAULT\logs"
$pidfile = Join-Path $logs "uvicorn_8000.pid"

function Kill-Pid([int]$id) {
  if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
    taskkill /PID $id /F | Out-Null
    return $true
  }
  return $false
}

$killed = $false

# 1) pidfile
if (Test-Path $pidfile) {
  $uvPid = (Get-Content $pidfile -First 1 | Out-String).Trim()
  if ($uvPid -match '^\d+$') {
    $killed = Kill-Pid ([int]$uvPid)
  }
}

# 2) por puerto
if (-not $killed) {
  $listen = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($pp in $listen) {
    if (Kill-Pid ([int]$pp)) { $killed = $true }
  }
}

# 3) por command line
if (-not $killed) {
  $procs = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'brain_server:app' -and $_.CommandLine -match '--port\s+8000' }
  foreach ($x in $procs) {
    if (Kill-Pid ([int]$x.ProcessId)) { $killed = $true }
  }
}

if ($killed) {
  Remove-Item -Force $pidfile -ErrorAction SilentlyContinue
  Write-Host "OK: detenido" -ForegroundColor Green
} else {
  Write-Host "OK: no había proceso escuchando en 8000" -ForegroundColor Yellow
}

netstat -ano | Select-String ":8000"
