param([string]$Msg, [string]$Sid='diag_r3')
$body = @{session_id=$Sid; message=$Msg} | ConvertTo-Json
$r = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 240
$r | ConvertTo-Json -Depth 6

