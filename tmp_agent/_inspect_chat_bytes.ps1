[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$body = @{ message='Hola, prueba breve para R8'; session_id='r8_inspect' } | ConvertTo-Json
$r = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method Post -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 60
Write-Host '--- TEXT (UTF8 console) ---'
Write-Host $r.response
Write-Host ''
Write-Host '--- FIRST 80 BYTES (hex) ---'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($r.response)
($bytes | Select-Object -First 80 | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
Write-Host ''
Write-Host "--- LEN bytes=$($bytes.Length) chars=$($r.response.Length) ---"
