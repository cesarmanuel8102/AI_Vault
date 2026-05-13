# Restart watchdog + brain so new autonomy env vars take effect
$ErrorActionPreference = 'Continue'

Write-Host "=== Step 1: Stop scheduled task if running ==="
try {
    Stop-ScheduledTask -TaskName 'AI_VAULT_BrainV9_AutoStart' -ErrorAction SilentlyContinue
    Write-Host "Scheduled task stop signal sent"
} catch { Write-Host "Stop-ScheduledTask: $_" }

Write-Host "`n=== Step 2: Terminate watchdog PID 66540 ==="
$wd = Get-CimInstance Win32_Process -Filter "ProcessId=66540" -ErrorAction SilentlyContinue
if ($wd) {
    $r = Invoke-CimMethod -InputObject $wd -MethodName Terminate
    Write-Host "Watchdog terminate ReturnValue: $($r.ReturnValue)"
} else {
    Write-Host "Watchdog 66540 not present"
}

Write-Host "`n=== Step 3: Terminate brain PID 49820 ==="
$br = Get-CimInstance Win32_Process -Filter "ProcessId=49820" -ErrorAction SilentlyContinue
if ($br) {
    $r = Invoke-CimMethod -InputObject $br -MethodName Terminate
    Write-Host "Brain terminate ReturnValue: $($r.ReturnValue)"
} else {
    Write-Host "Brain 49820 not present"
}

Start-Sleep -Seconds 5

Write-Host "`n=== Step 4: Start scheduled task ==="
Start-ScheduledTask -TaskName 'AI_VAULT_BrainV9_AutoStart'
Write-Host "Scheduled task started"

Write-Host "`n=== Step 5: Wait 90s for brain to come back up ==="
Start-Sleep -Seconds 90

Write-Host "`n=== Step 6: Health check ==="
try {
    $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/health' -TimeoutSec 10
    $h | ConvertTo-Json -Depth 5 | Write-Host
} catch {
    Write-Host "Health check failed: $_"
}

Write-Host "`n=== Step 7: Watchdog log tail ==="
Get-Content C:\AI_VAULT\tmp_agent\autostart_watchdog.log -Tail 15

Write-Host "`n=== Step 8: Find new brain process ==="
$conns = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $conns) {
    Write-Host "Port 8090 owned by PID $($c.OwningProcess)"
}
