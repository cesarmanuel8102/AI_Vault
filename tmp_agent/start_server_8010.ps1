$ErrorActionPreference="Stop"
$root="C:\AI_VAULT\00_identity"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "C:\AI_VAULT\tmp_agent\workspace\uvicorn_8010_$stamp.out.log"
$err = "C:\AI_VAULT\tmp_agent\workspace\uvicorn_8010_$stamp.err.log"
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

# limpia puerto
Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 300

$p = Start-Process -PassThru -FilePath "python" -WorkingDirectory $root -ArgumentList @(
  "-m","uvicorn","brain_server:app","--host","127.0.0.1","--port","8010","--log-level","info","--access-log"
) -RedirectStandardOutput $out -RedirectStandardError $err

"PID=$($p.Id)" | Write-Host
"OUT=$out" | Write-Host
"ERR=$err" | Write-Host

Start-Sleep -Milliseconds 700
Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8010/openapi.json" -TimeoutSec 3 |
  Select-Object -ExpandProperty StatusCode | Write-Host
