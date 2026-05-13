$r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8090/trading/qc-live/status -TimeoutSec 5
Write-Host "Status code: $($r.StatusCode)"
Write-Host "Body: $($r.Content)"
