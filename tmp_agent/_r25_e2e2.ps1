$ErrorActionPreference = "Continue"
$body = @{ session_id = "r25_e2e3"; message = "escanea mi red local 192.168.1.0/24" } | ConvertTo-Json
$t0 = Get-Date
try {
  $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 240
  $dt = ((Get-Date) - $t0).TotalSeconds
  Write-Host "ELAPSED: $([math]::Round($dt,1))s"
  Write-Host "ROUTE: $($resp.route)"
  Write-Host "INTENT: $($resp.intent)"
  Write-Host "TOOL_CALLS: $($resp.tool_calls)"
  Write-Host "---REPLY---"
  Write-Host $resp.reply
  Write-Host "---END---"
  $resp | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 C:/AI_VAULT/tmp_agent/_r25_e2e_resp.json
} catch {
  Write-Host "ERROR: $_"
}
