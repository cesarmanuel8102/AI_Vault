Write-Host "=== Verify scheduler config refreshed (CODE_MANAGED migration) ==="
$cfg = Get-Content 'C:\AI_VAULT\tmp_agent\state\scheduler_config.json' -Raw | ConvertFrom-Json
$ce = $cfg.tasks | Where-Object { $_.id -eq 'chat_excellence' }
if ($ce.prompt -match 'C:/AI_VAULT/tmp_agent/state') {
  Write-Host "OK: prompt has absolute path"
} else {
  Write-Host "BAD: prompt still has relative path"
}
if ($ce.prompt -match 'circuit_breaker.*ya existe' -or $ce.prompt -match 'NO propongas implementar') {
  Write-Host "OK: prompt mentions CB exists"
} else {
  Write-Host "BAD: prompt does not warn about CB"
}

Write-Host "`n=== Direct chat: ask brain to read enriched llm_metrics ==="
$prompt = @'
Lee el archivo C:/AI_VAULT/tmp_agent/state/brain_metrics/llm_metrics_latest.json
y responde SOLO con JSON estricto basado en lo que ves:
{
  "circuit_breaker_present": true|false,
  "cb_models_listed": [list of model_keys],
  "cb_open_count": N,
  "chain_health_present": true|false,
  "latency_per_model_present": true|false,
  "latency_models": [list of model_keys],
  "summary": "una frase sobre la salud que ves"
}
NO inventes. Si no puedes leer el archivo, di "READ_FAILED" en summary.
'@
$body = @{ session_id='r98_visibility2'; message=$prompt; model_priority='kimi_cloud' } | ConvertTo-Json
$start = Get-Date
try {
  $resp = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/chat' -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 240
  $elapsed = (Get-Date) - $start
  Write-Host ("OK ({0:N1}s) model={1}" -f $elapsed.TotalSeconds, $resp.model_used)
  Write-Host "`n--- BRAIN RESPONSE ---"
  Write-Host $resp.response
} catch {
  Write-Host "FAILED: $_"
}
