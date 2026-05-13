$cutoff = (Get-Date).AddDays(-2)
Get-ChildItem C:/AI_VAULT/tmp_agent -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -gt $cutoff -and $_.FullName -notmatch '\\(\.venv|node_modules|__pycache__|\.git)\\' } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 40 LastWriteTime, Length, FullName |
  Format-Table -AutoSize -Wrap
