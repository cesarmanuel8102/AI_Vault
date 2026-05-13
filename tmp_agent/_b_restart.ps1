$ErrorActionPreference = "Continue"
Write-Host "=== Killing existing brain on 8090 ===" -ForegroundColor Yellow
$conns = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $conns) {
    try {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host ("killed PID {0}" -f $c.OwningProcess)
    } catch {}
}
Start-Sleep -Seconds 3
Write-Host "=== Starting brain (manual, no watchdog) ===" -ForegroundColor Cyan
& "C:\AI_VAULT\tmp_agent\_manual_start.ps1"
