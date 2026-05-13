$body = @{ message = "/schedule run chat_excellence" } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 30
$r | ConvertTo-Json -Depth 4
