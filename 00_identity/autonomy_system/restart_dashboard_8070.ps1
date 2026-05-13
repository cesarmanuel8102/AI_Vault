$conn = Get-NetTCPConnection -LocalPort 8070 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
  $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
  if ($proc) {
    Stop-Process -Id $proc.Id -Force
    Start-Sleep -Seconds 1
  }
}

Start-Process -FilePath python -ArgumentList 'dashboard_server.py' -WorkingDirectory 'C:\AI_VAULT\00_identity\autonomy_system' -WindowStyle Hidden
Start-Sleep -Seconds 4
try {
  (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8070/api/health).Content
} catch {
  $_.Exception.Message
}
