# R18 smoke: trigger chat then tail event_log for chat.completed
$body = @{ message = "ping"; session_id = "smoke_r18" } | ConvertTo-Json -Compress
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host "CHAT_OK route_field=$($r.route) success=$($r.success)"
} catch {
    Write-Host "CHAT_ERR: $($_.Exception.Message)"
}
Start-Sleep -Seconds 1
$logPath = "C:/AI_VAULT/state/events/event_log.jsonl"
if (Test-Path $logPath) {
    Write-Host ""
    Write-Host "=== last chat.completed events ==="
    Get-Content $logPath -Tail 30 | Where-Object { $_ -match "chat\.completed" } | Select-Object -Last 5 | ForEach-Object {
        try {
            $o = $_ | ConvertFrom-Json
            Write-Host ("  route={0} sid={1} ok={2} dur_ms={3} resp_len={4} preview={5}" -f `
                $o.payload.route, $o.payload.session_id, $o.payload.success, $o.payload.duration_ms, $o.payload.response_len, ($o.payload.response_preview -replace "`n"," ").Substring(0, [Math]::Min(80, $o.payload.response_preview.Length)))
        } catch { Write-Host "  parse_err: $_" }
    }
} else {
    Write-Host "NO event_log at $logPath"
    # Try alt path
    $alt = "C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl"
    if (Test-Path $alt) {
        Write-Host "ALT path exists: $alt"
        Get-Content $alt -Tail 30 | Where-Object { $_ -match "chat\.completed" } | Select-Object -Last 5 | ForEach-Object {
            try {
                $o = $_ | ConvertFrom-Json
                Write-Host ("  route={0} sid={1} ok={2} dur_ms={3}" -f $o.payload.route, $o.payload.session_id, $o.payload.success, $o.payload.duration_ms)
            } catch {}
        }
    }
}
