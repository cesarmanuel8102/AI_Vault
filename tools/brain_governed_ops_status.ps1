param(
    [string]$EvidenceRoot = "tmp_agent/macro_front_brain_aggressive_governed_autonomy_excellence_01"
)
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo
$tags = @()
try { $tags = (Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5).models.name } catch { $tags = @("OLLAMA_UNREACHABLE") }
$probePath = Join-Path $EvidenceRoot "preflight.json"
$cyclePath = Join-Path $EvidenceRoot "cycles/cycle_summary.json"
$immutPath = Join-Path $EvidenceRoot "post_action_immutability_verify.json"
$result = [ordered]@{
  checked_utc = (Get-Date).ToUniversalTime().ToString("o")
  provider = [ordered]@{
    kimi_k2_6_present = ($tags -contains "kimi-k2.6:cloud")
    last_provider_probe = if (Test-Path $probePath) { Get-Content $probePath -Raw | ConvertFrom-Json | Select-Object -ExpandProperty provider_probe } else { $null }
  }
  memory_faiss = if (Test-Path $immutPath) { Get-Content $immutPath -Raw | ConvertFrom-Json } else { $null }
  operations_queue = if (Test-Path "tmp_agent/brain_v9/operations/operation_queue.jsonl") { (Get-Content "tmp_agent/brain_v9/operations/operation_queue.jsonl" | Measure-Object -Line).Lines } else { 0 }
  last_cycle_summary = if (Test-Path $cyclePath) { Get-Content $cyclePath -Raw | ConvertFrom-Json } else { $null }
  next_recommended_human_action = "Review next FRONT-BRAIN-DAILY-AUTONOMOUS-OPERATIONS-DRYRUN-01 prompt."
  secrets_printed = $false
}
$result | ConvertTo-Json -Depth 8
