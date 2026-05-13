$body = @{session_id="test_agent"; message="lista los archivos en C:/AI_VAULT/tmp_agent/brain_v9/agent"} | ConvertTo-Json
$r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 120
Write-Host ("success={0} len={1}" -f $r.success, $r.response.Length)
Write-Host $r.response.Substring(0, [Math]::Min(500, $r.response.Length))
