$ErrorActionPreference = "Continue"
$body = @{ session_id = "r26_e2e_v3"; message = "usa nmap para escanear 192.168.1.0/24 y dime cuantos hosts hay" } | ConvertTo-Json
$t0 = Get-Date
try {
  $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 240
  $dt = ((Get-Date) - $t0).TotalSeconds
  Write-Host "ELAPSED: $([math]::Round($dt,1))s"
  Write-Host "MODEL: $($resp.model_used)"
  Write-Host "---REPLY---"
  Write-Host $resp.response
  Write-Host "---END---"
  $resp | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 C:/AI_VAULT/tmp_agent/_r26_e2e_v3_resp.json
} catch {
  Write-Host "ERROR: $_"
}
