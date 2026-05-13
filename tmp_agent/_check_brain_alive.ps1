Get-Process python -ErrorAction SilentlyContinue |
  Select-Object Id, StartTime, @{n='MemMB';e={[math]::Round($_.WorkingSet64/1MB,1)}} |
  Format-Table -AutoSize
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
  Select-Object State, OwningProcess | Format-Table -AutoSize
