$path = 'C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl'
$lines = Get-Content $path -Tail 4000
$timing = $lines | Where-Object { $_ -match 't1_scan' -or $_ -match 'fast_synthesize' -or $_ -match 'leak_tail' -or $_ -match 'agent.step.timing' } | Select-Object -Last 30
foreach ($l in $timing) {
    try {
        $e = $l | ConvertFrom-Json
        Write-Host ("[{0}] {1}" -f $e.name, ($e.payload | ConvertTo-Json -Compress -Depth 3))
    } catch {}
}
