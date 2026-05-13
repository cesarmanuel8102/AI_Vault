$ErrorActionPreference = "Continue"
$body_template = @{ message = ""; session_id = "r4_persist_trigger" }

# Mix of queries - some trivial, one designed to trigger tool_name_corrected if LLM
# tries to use a known alias
$queries = @(
  "hola",
  "que dia es hoy",
  "1+1",
  "dime un color",
  "cuanto es 3*3",
  "lista los archivos en C:/AI_VAULT/tmp_agent con el comando 'list_dir'"
)

$i = 0
foreach ($q in $queries) {
  $i++
  $body = @{ message = $q; session_id = "r4_persist_trigger_$i" } | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST `
      -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host "[$i] OK route=$($r.route) latency=$($r.latency_ms)ms"
  } catch {
    Write-Host "[$i] FAIL: $_"
  }
}

Write-Host "`n--- Final metrics ---"
Get-Content "C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json"
