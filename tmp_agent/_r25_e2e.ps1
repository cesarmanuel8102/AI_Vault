$ErrorActionPreference = "Stop"
$body = @{ session_id = "r25_e2e"; message = "escanea mi red local 192.168.1.0/24" } | ConvertTo-Json
$t0 = Get-Date
$resp = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 180
$dt = ((Get-Date) - $t0).TotalSeconds
[pscustomobject]@{
  elapsed_s = [math]::Round($dt,1)
  route     = $resp.route
  intent    = $resp.intent
  reply_head = ($resp.reply -split "`n")[0..3] -join " | "
} | ConvertTo-Json
