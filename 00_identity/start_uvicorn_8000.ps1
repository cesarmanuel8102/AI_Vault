$ErrorActionPreference = "Stop"

$work = "C:\AI_VAULT\00_identity"
$logs = "C:\AI_VAULT\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$ts      = Get-Date -Format "yyyyMMdd_HHmmss"
$uvout   = Join-Path $logs "uvicorn_8000_out_$ts.txt"
$uverr   = Join-Path $logs "uvicorn_8000_err_$ts.txt"
$pidfile = Join-Path $logs "uvicorn_8000.pid"
$metaj   = Join-Path $logs "uvicorn_8000.meta.json"

# Pre-flight: si ya hay LISTEN, abortar sin tumbar la consola
$listen = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

if ($listen) {
  Write-Host "ERROR: Ya existe LISTEN en 8000. PID(s): $($listen -join ', ')" -ForegroundColor Red
  return
}

$p = Start-Process -FilePath "python" `
  -ArgumentList @("-m","uvicorn","brain_server:app","--host","127.0.0.1","--port","8000") `
  -WorkingDirectory $work `
  -RedirectStandardOutput $uvout `
  -RedirectStandardError  $uverr `
  -NoNewWindow -PassThru

$p.Id | Set-Content -Encoding ascii $pidfile
@{
  pid        = $p.Id
  started_at = (Get-Date).ToString("o")
  workdir    = $work
  out        = $uvout
  err        = $uverr
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $metaj

Start-Sleep -Seconds 1

$listen2 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

if (-not $listen2 -or ($listen2 -notcontains $p.Id)) {
  Write-Host "ERROR: Uvicorn no quedó escuchando en 8000. Tail ERR:" -ForegroundColor Red
  if (Test-Path $uverr) { Get-Content $uverr -Tail 120 }
  return
}

Write-Host "OK: Uvicorn LISTEN 8000 PID=$($p.Id)" -ForegroundColor Green
Write-Host "OUT: $uvout"
Write-Host "ERR: $uverr"
