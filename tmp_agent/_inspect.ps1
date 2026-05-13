$body = @{ message='que hora es'; session_id='inspect' } | ConvertTo-Json
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/chat' -Method POST -Body $body -ContentType 'application/json' -TimeoutSec 60
$r | ConvertTo-Json -Depth 6 | Out-File C:/AI_VAULT/tmp_agent/_inspect_chat.json -Encoding utf8
Write-Host "FIELDS:"
($r | Get-Member -MemberType NoteProperty).Name
Write-Host "`nFULL:"
$r | ConvertTo-Json -Depth 6
