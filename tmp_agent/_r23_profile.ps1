$path = 'C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl'
$lines = Get-Content $path -Tail 2000
$timing = $lines | Where-Object { $_ -match 'agent.step.timing' } | Select-Object -Last 12
Write-Host "Last $($timing.Count) timing events:"
foreach ($l in $timing) {
    try {
        $e = $l | ConvertFrom-Json
        $p = $e.payload
        Write-Host ("step={0} obs={1}ms reason={2}ms act={3}ms verify={4}ms total={5}ms tools={6}" -f `
            $p.step, $p.observe_ms, $p.reason_ms, $p.act_ms, $p.verify_ms, $p.total_ms, ($p.tools -join ','))
    } catch { Write-Host "PARSE FAIL: $l" }
}
