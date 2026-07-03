# _test_chat_modes.ps1 — Phase 6 chat mode validation (read-only POST probes)
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8092/brain-dashboard/chat"

function Test-Mode([string]$mode, [string]$msg) {
  try {
    $body = @{ message=$msg; mode=$mode; user_id="test_validator" } | ConvertTo-Json -Compress
    $r = Invoke-WebRequest -Uri $base -Method Post -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 15
    $j = $r.Content | ConvertFrom-Json
    $summary = @{
      mode_requested = if ($j.mode_requested) { $j.mode_requested } else { "NOT_RETURNED" }
      mode_effective = if ($j.mode_effective) { $j.mode_effective } else { "NOT_RETURNED" }
      auto_decision  = if ($j.auto_decision)  { $j.auto_decision } else { "NOT_RETURNED" }
      escalation     = $j.mode_escalation_required
      status         = $j.status
      run_id_ok      = [bool]$j.run_id
      content_ok     = [bool]$j.content
      fallback_reason= $j.fallback_reason
      provider_degraded = $j.provider_degraded
      blocked_tools  = if ($j.blocked_tools) { ($j.blocked_tools -join ',') } else { "none" }
    }
    "PASS  mode=$mode  req=$($summary.mode_requested)  eff=$($summary.mode_effective)  auto=$($summary.auto_decision)  esc=$($summary.escalation)  status=$($summary.status)  run_id=$($summary.run_id_ok)  content=$($summary.content_ok)  degraded=$($summary.provider_degraded)  fallback=$($summary.fallback_reason)  blocked=$($summary.blocked_tools)"
  } catch {
    $code = $null
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    "FAIL  mode=$mode  code=$code  ($($_.Exception.Message))"
  }
}

Test-Mode "read_only" "hola"
Test-Mode "build" "draft a safe plan, do not modify files"
Test-Mode "auto" "test auto mode"