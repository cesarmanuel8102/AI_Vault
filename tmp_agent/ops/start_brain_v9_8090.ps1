$root = "C:\AI_VAULT\tmp_agent"
$logs = Join-Path $root "ops\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outLog = Join-Path $logs "brain_v9_8090_$ts.out.log"
$errLog = Join-Path $logs "brain_v9_8090_$ts.err.log"

$owning = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
if ($owning) {
    try { Stop-Process -Id $owning -Force -ErrorAction Stop } catch {}
    Start-Sleep -Seconds 2
}

$cmd = 'Set-Location "C:\AI_VAULT\tmp_agent"; python -m brain_v9.main'
$proc = Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd) -PassThru -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Start-Sleep -Seconds 8

$health = $null
try {
    $health = Invoke-RestMethod -TimeoutSec 5 -Uri "http://127.0.0.1:8090/health"
} catch {}

[pscustomobject]@{
    ok = [bool]$health
    pid = $proc.Id
    out_log = $outLog
    err_log = $errLog
    health = $health
} | ConvertTo-Json -Depth 5
