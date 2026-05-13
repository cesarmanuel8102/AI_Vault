$logs    = "C:\AI_VAULT\logs"
$pidfile = Join-Path $logs "uvicorn_8000.pid"
$meta    = Join-Path $logs "uvicorn_8000.meta.json"

"--- PORT 8000 ---"
netstat -ano | Select-String ":8000"

"--- PIDFILE ---"
if (Test-Path $pidfile) { Get-Content $pidfile } else { "(no pidfile)" }

"--- META ---"
if (Test-Path $meta) { Get-Content $meta } else { "(no meta)" }
