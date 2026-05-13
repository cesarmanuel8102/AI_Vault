$base = 'http://127.0.0.1:8090'

function Try-Get($path) {
    try {
        $r = Invoke-RestMethod -Uri "$base$path" -TimeoutSec 15
        Write-Host "`n=== GET $path ==="
        $r | ConvertTo-Json -Depth 6 -Compress | Write-Host
    } catch {
        Write-Host "`n=== GET $path  -> ERROR: $($_.Exception.Message) ==="
    }
}

Try-Get '/health'
Try-Get '/brain/autonomy/status'
Try-Get '/brain/proactive/status'
Try-Get '/brain/proactive/tasks'
Try-Get '/brain/roadmap'
Try-Get '/brain/governance/health'
Try-Get '/brain/self_diagnostic/status'
Try-Get '/brain/utility'
Try-Get '/brain/validators'
