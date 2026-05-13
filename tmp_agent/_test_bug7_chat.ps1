$body = @{
    message = "busca archivos *.py en C:/AI_VAULT/00_identity"
    session_id = "bug7_test_" + [DateTimeOffset]::Now.ToUnixTimeSeconds()
} | ConvertTo-Json

$resp = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 120
Write-Host "===== REPLY ====="
Write-Host $resp.reply
Write-Host ""
Write-Host "===== META ====="
$resp | ConvertTo-Json -Depth 4 | Out-String | Write-Host
