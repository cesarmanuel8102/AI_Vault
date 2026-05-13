$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 3
$artifact = 'C:\AI_VAULT\tmp_agent\brain_v9\ops\restart_brain_v9_result_20260331_221842.json'
$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
  try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep -Seconds 2
$env:PYTHONUNBUFFERED = '1'
$env:BRAIN_SAFE_MODE = 'false'
$env:BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS = 'true'
$env:BRAIN_CHAT_DEV_MODE = 'true'
$env:BRAIN_START_AUTONOMY = 'true'
$env:BRAIN_START_PROACTIVE = 'true'
$env:BRAIN_START_SELF_DIAGNOSTIC = 'true'
$env:BRAIN_START_QC_LIVE_MONITOR = 'true'
$env:BRAIN_WARMUP_MODEL = 'true'
$env:LLM_TIMEOUT = '240'
$env:LLM_AGENT_TIMEOUT = '300'
$env:SELF_DEV_ENABLED = '1'
$env:SELF_DEV_REQUIRE_APPROVAL = '0'
if (-not $env:SELF_DEV_MAX_RISK) { $env:SELF_DEV_MAX_RISK = '0.4' }
if (-not $env:PAD_MFA_TEST_OVERRIDE) { $env:PAD_MFA_TEST_OVERRIDE = 'test_pad_2026' }
$p = Start-Process -FilePath python -ArgumentList '-u','-m','brain_v9.main' -WorkingDirectory 'C:\AI_VAULT\tmp_agent' -WindowStyle Hidden -PassThru
$ok = $false
$status = $null
for ($i = 0; $i -lt 25; $i++) {
  Start-Sleep -Seconds 1
  try {
    $resp = Invoke-RestMethod 'http://127.0.0.1:8090/health' -TimeoutSec 3
    $status = $resp.status
    if ($resp.status -eq 'healthy') { $ok = $true; break }
  } catch {}
}
@{
  ok = $ok
  pid = $p.Id
  health_status = $status
  artifact_generated_at = (Get-Date).ToString('s')
} | ConvertTo-Json -Depth 4 | Set-Content $artifact -Encoding UTF8
