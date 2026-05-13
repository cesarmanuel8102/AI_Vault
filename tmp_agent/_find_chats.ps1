$cutoff = (Get-Date).AddHours(-12)
Write-Host "=== Files with chat/conv/session/message in name modified in last 12h ==="
Get-ChildItem C:/AI_VAULT/tmp_agent -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object {
    $_.LastWriteTime -gt $cutoff -and
    $_.FullName -notmatch '\\(\.venv|node_modules|__pycache__|\.git)\\' -and
    $_.Name -match '(chat|conv|session|room|message|dialog|thread)'
  } |
  Sort-Object LastWriteTime -Descending |
  Select-Object LastWriteTime, Length, FullName |
  Format-Table -AutoSize -Wrap

Write-Host ""
Write-Host "=== state/ subdirs sorted by most recent file ==="
Get-ChildItem C:/AI_VAULT/tmp_agent/state -Directory | ForEach-Object {
  $latest = Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($latest) {
    [PSCustomObject]@{ Dir = $_.Name; Latest = $latest.LastWriteTime; File = $latest.Name }
  }
} | Sort-Object Latest -Descending | Format-Table -AutoSize
