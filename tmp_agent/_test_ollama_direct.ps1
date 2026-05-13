# Direct test: ¿Ollama kimi_cloud devuelve mojibake o solo via Brain?
$body = @{
    model='kimi-k2.5:cloud'
    messages=@(@{role='user'; content='Responde con la palabra: diagnósticos análisis'})
    stream=$false
    options=@{ num_predict=64 }
} | ConvertTo-Json -Depth 5

$r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/chat' -Method Post -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 60 -UseBasicParsing
$rawBytes = $r.RawContentStream.ToArray()
Write-Host "--- RAW BYTES (first 200 hex) ---"
($rawBytes | Select-Object -First 200 | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
Write-Host ''
Write-Host '--- DECODED AS UTF-8 ---'
[System.Text.Encoding]::UTF8.GetString($rawBytes)
