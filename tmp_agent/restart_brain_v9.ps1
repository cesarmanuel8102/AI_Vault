$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
  $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
  if ($proc) {
    Stop-Process -Id $proc.Id -Force
    Start-Sleep -Seconds 1
  }
}

Start-Process -FilePath python -ArgumentList '-m','brain_v9.main' -WorkingDirectory 'C:\AI_VAULT\tmp_agent' -WindowStyle Hidden
Start-Sleep -Seconds 4
try {
  (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8090/health).Content
} catch {
  $_.Exception.Message
}
