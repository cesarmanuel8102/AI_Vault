Write-Host "=== Force chat_excellence iter#2 ==="
$run = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/proactive/run/chat_excellence' -Method POST
$run | ConvertTo-Json -Depth 4

$historyPath = 'C:\AI_VAULT\tmp_agent\state\chat_excellence_history.json'
$before = 0
if (Test-Path $historyPath) {
  $h = Get-Content $historyPath -Raw | ConvertFrom-Json
  $before = $h.Count
}
Write-Host "`nBaseline iterations: $before"

Write-Host "`n=== Polling chat_excellence/status until new iter (max 12min) ==="
$deadline = (Get-Date).AddMinutes(12)
$iter = $null
while ((Get-Date) -lt $deadline) {
  Start-Sleep 30
  $st = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/chat_excellence/status' -Method GET
  $now = Get-Date -Format 'HH:mm:ss'
  Write-Host "[$now] total=$($st.total_iterations) parsed_ratio=$($st.parsed_ratio)"
  if ($st.total_iterations -gt $before) {
    $iter = $st.latest
    break
  }
}

if ($null -eq $iter) {
  Write-Host "TIMEOUT: no new iteration after 12min"
  exit 1
}

Write-Host "`n=== NEW ITERATION (#$($iter.iter)) ==="
Write-Host "model_used   : $($iter.model_used)"
Write-Host "elapsed_s    : $($iter.elapsed_s)"
Write-Host "success      : $($iter.success)"
Write-Host "parsed_ok    : $($iter.parsed_ok)"
Write-Host "impact_score : $($iter.impact_score)"
Write-Host "status       : $($iter.status)"
Write-Host "`nweakness     : $($iter.weakness)"
Write-Host "`nroot_cause   : $($iter.root_cause_guess)"
Write-Host "`nproposed     : $($iter.proposed_change)"
Write-Host "`ntest_plan    : $($iter.test_plan)"
Write-Host "`nexpected     : $($iter.expected_improvement)"
Write-Host "`naffected     : $($iter.affected_files -join ', ')"

Write-Host "`n=== KEY CHECK: did brain reference EXISTING CB? ==="
$txt = "$($iter.weakness) $($iter.root_cause_guess) $($iter.proposed_change)".ToLower()
$mentionsExisting = ($txt -match 'circuit breaker.*(existe|existing|ya|already|current)' -or
                    $txt -match '(existe|existing|already).*circuit')
$proposesNewCB = ($txt -match 'implement.*circuit breaker' -or
                  $txt -match 'add.*circuit breaker' -or
                  $txt -match 'crear.*circuit breaker' -or
                  $txt -match 'a-adir.*circuit breaker')
Write-Host "Mentions existing CB: $mentionsExisting"
Write-Host "Proposes NEW CB (red flag): $proposesNewCB"
