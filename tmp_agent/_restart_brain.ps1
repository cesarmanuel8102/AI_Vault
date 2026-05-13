Stop-Process -Id 62680 -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-30) } | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Write-Host "killed PID $($_.Id)"
}
Start-Sleep -Seconds 3
# Relaunch watchdog
Start-Process -WindowStyle Hidden powershell.exe -ArgumentList '-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','C:\AI_VAULT\tmp_agent\autostart_brain_v9.ps1'
Write-Host "watchdog relaunched"
Start-Sleep -Seconds 50
$h = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 30
Write-Host "Brain health: $($h.status), safe_mode=$($h.safe_mode)"
