$body = @{session_id="quick"; message="que hora es"} | ConvertTo-Json
$r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
Write-Host ("success={0} len={1}" -f $r.success, $r.response.Length)
Write-Host $r.response.Substring(0, [Math]::Min(150, $r.response.Length))
