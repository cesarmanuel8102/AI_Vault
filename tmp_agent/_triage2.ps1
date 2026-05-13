Write-Host "=== ALL scheduled tasks active in last 10 min ==="
$start = (Get-Date).AddMinutes(-30)
Get-ScheduledTask | ForEach-Object {
  $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath -ErrorAction SilentlyContinue
  if ($info -and $info.LastRunTime -gt $start) {
    [pscustomobject]@{
      TaskName = $_.TaskName
      LastRun  = $info.LastRunTime
      Result   = $info.LastTaskResult
      State    = $_.State
    }
  }
} | Sort-Object LastRun -Descending | Format-Table -AutoSize

Write-Host ""
Write-Host "=== Any leftover BrainHealthGate_* ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like 'BrainHealth*' } | Select TaskName,State

Write-Host ""
Write-Host "=== Brain v9 main.py exit handlers / shutdown ==="
Select-String -Path C:/AI_VAULT/tmp_agent/brain_v9/main.py -Pattern '_exit|signal\.|atexit|shutdown' | Select-Object -First 15 LineNumber,Line | Format-Table -AutoSize
