$base = 'http://127.0.0.1:8090'

function Try-Get($path, $depth = 6) {
    Write-Host "`n=== GET $path ==="
    try {
        $r = Invoke-RestMethod -Uri "$base$path" -TimeoutSec 15
        $r | ConvertTo-Json -Depth $depth | Write-Host
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)"
    }
}

Try-Get '/health' 3
Try-Get '/brain/proactive/status' 5
Try-Get '/brain/chat_excellence/status' 6
