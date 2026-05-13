$m = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/validators' -TimeoutSec 10
Write-Host "=== live_module_counters ==="
$m.live_module_counters | ConvertTo-Json -Depth 3
Write-Host ""
Write-Host "=== Filtered new metrics ==="
$keys = @('auto_rewrite_hit', 'auto_rewrite_ps_dollar', 'auto_rewrite_failed', 'anti_ghost_force_replan', 'step_truncation_aggressive', 'fast_synthesize_hit')
foreach ($k in $keys) {
    $v = $m.live_module_counters.$k
    Write-Host "  $k = $v"
}
