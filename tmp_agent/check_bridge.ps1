try {
    $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/status
    Write-Host $r.Content
} catch {
    Write-Host "Bridge not responding: $($_.Exception.Message)"
}
