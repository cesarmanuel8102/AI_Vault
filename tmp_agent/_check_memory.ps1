Write-Host "=== state/memory/ recent ==="
Get-ChildItem C:/AI_VAULT/tmp_agent/state/memory -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-2) } |
  Sort-Object LastWriteTime -Descending |
  Select-Object LastWriteTime, Length, FullName |
  Format-Table -AutoSize -Wrap

Write-Host ""
Write-Host "=== All memory subdirs ==="
Get-ChildItem C:/AI_VAULT/tmp_agent/state/memory -Directory -ErrorAction SilentlyContinue |
  ForEach-Object {
    $st = Join-Path $_.FullName "short_term.json"
    if (Test-Path $st) {
      $info = Get-Item $st
      [PSCustomObject]@{ Session = $_.Name; LastWrite = $info.LastWriteTime; Bytes = $info.Length }
    }
  } | Sort-Object LastWrite -Descending | Format-Table -AutoSize
