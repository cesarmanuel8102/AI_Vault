Write-Host "=== Trigger quick chat to populate LLM metrics ==="
$body = @{ session_id = 'r98_validation'; message = 'di hola en una palabra'; model_priority = 'kimi_cloud' } | ConvertTo-Json
$start = Get-Date
try {
  $resp = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/chat' -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 60
  $elapsed = (Get-Date) - $start
  Write-Host ("OK ({0:N1}s) model={1}" -f $elapsed.TotalSeconds, $resp.model_used)
  Write-Host ("Response: " + $resp.response.Substring(0, [Math]::Min(80, $resp.response.Length)))
} catch {
  Write-Host "Chat failed: $_"
}

Write-Host "`n=== Wait 5s for metrics persistence (every 3 queries) ==="
Start-Sleep 5

# Trigger 2 more to ensure _PERSIST_EVERY=3 fires
1..2 | ForEach-Object {
  $body = @{ session_id = "r98_v$_"; message = "ping $_"; model_priority = 'kimi_cloud' } | ConvertTo-Json
  try { Invoke-RestMethod -Uri 'http://127.0.0.1:8090/chat' -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 60 | Out-Null; Write-Host "ping $_ OK" } catch { Write-Host "ping $_ FAIL" }
}

Start-Sleep 3

Write-Host "`n=== R9.8: Read enriched llm_metrics_latest.json ==="
$path = 'C:\AI_VAULT\tmp_agent\state\brain_metrics\llm_metrics_latest.json'
if (Test-Path $path) {
  $m = Get-Content $path -Raw | ConvertFrom-Json
  Write-Host "Keys present: $($m.PSObject.Properties.Name -join ', ')"
  Write-Host "`ncircuit_breaker:"
  $m.circuit_breaker | ConvertTo-Json -Depth 5
  Write-Host "`nchain_health:"
  $m.chain_health | ConvertTo-Json -Depth 5
  Write-Host "`nlatency_per_model:"
  $m.latency_per_model | ConvertTo-Json -Depth 4
} else {
  Write-Host "FILE NOT FOUND: $path"
}

Write-Host "`n=== R9.9: CB endpoint (after queries) ==="
Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/llm/circuit_breaker' -Method GET | ConvertTo-Json -Depth 5
