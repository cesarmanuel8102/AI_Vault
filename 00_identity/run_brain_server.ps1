$ErrorActionPreference = 'Continue'

$BASE   = 'C:\AI_VAULT\00_identity'
$VPY    = 'C:\AI_VAULT\00_identity\.venv\Scripts\python.exe'
$OUTLOG = 'C:\AI_VAULT\00_identity\logs\uvicorn_out.log'
$ERRLOG = 'C:\AI_VAULT\00_identity\logs\uvicorn_err.log'
$SYSLOG = 'C:\Windows\Temp\brain_server_SYSTEM.log'

function LogSys([string]$m) {
  try { "[{0}] {1}" -f (Get-Date -Format s), $m | Add-Content -Encoding UTF8 $SYSLOG } catch {}
}

"START 2026-02-19T19:16:30" | Set-Content -Encoding UTF8 $SYSLOG
LogSys "BASE=$BASE"
LogSys "VPY=$VPY"
LogSys "OUTLOG=$OUTLOG"
LogSys "ERRLOG=$ERRLOG"

if (!(Test-Path $BASE)) { LogSys "BASE_MISSING"; exit 11 }
if (!(Test-Path $VPY))  { LogSys "VPY_MISSING";  exit 12 }

# Evita doble instancia
try {
  if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    LogSys "PORT_ALREADY_LISTEN"
    exit 0
  }
} catch { LogSys "GETNETTCP_FAIL: $(.Exception.Message)" }

# Limpia logs (opcional)
try { if (Test-Path $OUTLOG) { Clear-Content $OUTLOG } } catch {}
try { if (Test-Path $ERRLOG) { Clear-Content $ERRLOG } } catch {}

Set-Location $BASE

# IMPORTANT: TODO en una sola línea (para que NO se rompa -ArgumentList)
try {
  $p = Start-Process -FilePath $VPY -ArgumentList @('-m','uvicorn','brain_server:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $BASE -WindowStyle Hidden -RedirectStandardOutput $OUTLOG -RedirectStandardError $ERRLOG -PassThru
  LogSys "START_PROCESS_OK PID=$($p.Id)"
} catch {
  LogSys "START_PROCESS_FAIL: $(.Exception.Message)"
  exit 21
}

Start-Sleep 2

try {
  if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    LogSys "LISTEN_OK"
    exit 0
  } else {
    LogSys "LISTEN_NO"
  }
} catch { LogSys "LISTEN_CHECK_FAIL: $(.Exception.Message)" }

# Si no escucha, añade tail de ERRLOG
try {
  if (Test-Path $ERRLOG) {
    $tail = (Get-Content $ERRLOG -Tail 60 -ErrorAction SilentlyContinue) -join ' | '
    if ($tail) { LogSys "ERR_TAIL=$tail" }
  }
} catch {}

exit 3
