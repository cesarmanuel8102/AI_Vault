# Triage brain crash-loop

Write-Host "=== 1. Last 25 lines of latest brain stderr (PID 81816) ==="
$latest = Get-ChildItem C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "File: $($latest.FullName)"
Write-Host "Size: $($latest.Length) bytes  LastWrite: $($latest.LastWriteTime)"
Get-Content $latest.FullName -Tail 25
Write-Host ""

Write-Host "=== 2. Windows Event Log: app crashes / kills 14:25-14:32 ==="
$start = [DateTime]"2026-05-04 14:25:00"
$end   = [DateTime]"2026-05-04 14:32:00"
try {
  Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$start; EndTime=$end} -ErrorAction Stop |
    Where-Object { $_.Message -match 'python|brain|81816|62728|82248|81404' } |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, @{n='Msg';e={$_.Message.Substring(0,[Math]::Min(220,$_.Message.Length))}} |
    Format-List
} catch {
  Write-Host "Application log query error: $($_.Exception.Message)"
}
Write-Host ""

Write-Host "=== 3. System log: process kills / OOM ==="
try {
  Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$start; EndTime=$end} -ErrorAction Stop |
    Where-Object { $_.Message -match 'python|memory|terminate' } |
    Select-Object TimeCreated, Id, ProviderName, @{n='Msg';e={$_.Message.Substring(0,[Math]::Min(220,$_.Message.Length))}} |
    Format-List
} catch {
  Write-Host "System log query error: $($_.Exception.Message)"
}
Write-Host ""

Write-Host "=== 4. Memory snapshot ==="
$os = Get-CimInstance Win32_OperatingSystem
$totalGB = [Math]::Round($os.TotalVisibleMemorySize/1MB, 2)
$freeGB  = [Math]::Round($os.FreePhysicalMemory/1MB, 2)
Write-Host "Total RAM: ${totalGB} GB  Free: ${freeGB} GB  Used: $([Math]::Round($totalGB-$freeGB,2)) GB"
Write-Host ""

Write-Host "=== 5. Top memory consumers ==="
Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 Name,Id,@{n='MemMB';e={[Math]::Round($_.WS/1MB,1)}} | Format-Table -AutoSize
