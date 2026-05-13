$root = "C:\AI_VAULT\tmp_agent"
$logs = Join-Path $root "ops\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outLog = Join-Path $logs "pocketoption_bridge_8765_$ts.out.log"
$errLog = Join-Path $logs "pocketoption_bridge_8765_$ts.err.log"

$existing = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -like "*pocketoption_bridge_server.py*") -or
    ($_.CommandLine -like "*brain_v9.trading.pocketoption_bridge_server*")
}
foreach ($proc in $existing) {
    try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop } catch {}
}

$cmd = 'Set-Location "C:\AI_VAULT\tmp_agent"; python -m brain_v9.trading.pocketoption_bridge_server'
$proc = Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd) -PassThru -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Start-Sleep -Seconds 3

$health = $null
try {
    $health = Invoke-RestMethod -TimeoutSec 5 -Uri "http://127.0.0.1:8765/healthz"
} catch {}

[pscustomobject]@{
    ok = [bool]$health
    pid = $proc.Id
    out_log = $outLog
    err_log = $errLog
    health = $health
} | ConvertTo-Json -Depth 5
