# Hypothesis: McAfee or another security tool killing python
Write-Host "=== Security tool processes ==="
Get-Process | Where-Object { $_.ProcessName -match 'mcafee|defender|MsMpEng|avg|avast|norton|kaspersky|bit ?def' } |
  Select-Object Name,Id,@{n='MemMB';e={[Math]::Round($_.WS/1MB,1)}} | Format-Table -AutoSize

Write-Host ""
Write-Host "=== Defender / Security event log ==="
$start = [DateTime]"2026-05-04 14:25:00"
$end   = [DateTime]"2026-05-04 14:32:00"
$logs = @('Microsoft-Windows-Windows Defender/Operational','Microsoft-Windows-Security-Mitigations/KernelMode')
foreach ($log in $logs) {
  Write-Host "  -- Log: $log --"
  try {
    Get-WinEvent -FilterHashtable @{LogName=$log; StartTime=$start; EndTime=$end} -ErrorAction Stop |
      Select-Object -First 5 TimeCreated,Id,@{n='Msg';e={$_.Message.Substring(0,[Math]::Min(180,$_.Message.Length))}} |
      Format-List
  } catch {
    Write-Host "    (no events / log unavailable: $($_.Exception.Message.Substring(0,[Math]::Min(80,$_.Exception.Message.Length))))"
  }
}

Write-Host ""
Write-Host "=== Security log: process termination 4689 (audit must be enabled to see anything) ==="
try {
  Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4689; StartTime=$start; EndTime=$end} -ErrorAction Stop |
    Where-Object { $_.Message -match 'python' } |
    Select-Object -First 5 TimeCreated,@{n='Msg';e={$_.Message.Substring(0,[Math]::Min(220,$_.Message.Length))}} | Format-List
} catch {
  Write-Host "  No 4689 events (process termination audit not enabled)"
}
