$prompt = @"
Lee el archivo C:/AI_VAULT/tmp_agent/state/brain_metrics/llm_metrics_latest.json
y responde EN JSON ESTRICTO basado SOLO en lo que ves:
{
  "circuit_breaker_present": true|false,
  "cb_models_listed": [...],
  "cb_open_count": N,
  "chain_health_present": true|false,
  "latency_per_model_present": true|false,
  "latency_models": [...],
  "summary": "una frase: que ves sobre la salud de modelos"
}
NO inventes datos. Si una clave no existe, ponla en false/empty.
"@

$body = @{
  session_id = 'r98_brain_visibility'
  message = $prompt
  model_priority = 'kimi_cloud'
} | ConvertTo-Json

Write-Host "=== Asking brain what it SEES in llm_metrics_latest.json ==="
$start = Get-Date
try {
  $resp = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/chat' -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 180
  $elapsed = (Get-Date) - $start
  Write-Host ("OK ({0:N1}s) model={1}" -f $elapsed.TotalSeconds, $resp.model_used)
  Write-Host "`n--- BRAIN RESPONSE ---"
  Write-Host $resp.response
} catch {
  Write-Host "FAILED: $_"
}
