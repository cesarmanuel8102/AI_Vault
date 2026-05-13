$base = "http://127.0.0.1:8090"

# 1. Coverage at startup (should be empty or minimal)
Write-Host "===== T1: GET /tools/coverage at startup ====="
$r0 = Invoke-RestMethod -Uri "$base/tools/coverage" -Method Get -TimeoutSec 10
Write-Host "totals: $($r0.totals | ConvertTo-Json -Compress)"
Write-Host "tools tracked: $($r0.tools.PSObject.Properties.Count)"

# 2. Trigger several tool invocations via chat
$queries = @(
    "que version de python tengo",
    "que espacio libre tengo en disco",
    "que servicios estan corriendo",
    "busca archivos *.py en C:/AI_VAULT/00_identity",
    "busca archivos con errores"  # this should trigger missing_args
)
foreach ($q in $queries) {
    $body = @{ message = $q; session_id = "r14_smoke_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host "  sent: $q"
}

# 3. Coverage after invocations
Write-Host ""
Write-Host "===== T2: GET /tools/coverage after invocations ====="
$r1 = Invoke-RestMethod -Uri "$base/tools/coverage" -Method Get -TimeoutSec 10
Write-Host "totals:"
$r1.totals | Format-List
Write-Host "top_failing:"
$r1.top_failing | ForEach-Object {
    Write-Host "  - $($_.tool): failures=$($_.failures) schema_violations=$($_.schema_violations) error_types=$($_.error_types | ConvertTo-Json -Compress)"
}
Write-Host "tools tracked:"
$r1.tools.PSObject.Properties | ForEach-Object {
    $stats = $_.Value
    Write-Host ("  - {0,-30} inv={1} succ={2} fail={3} schema={4} trunc={5} avg_ms={6} vskip={7}" -f $_.Name, $stats.invocations, $stats.successes, $stats.failures, $stats.schema_violations, $stats.truncations, $stats.avg_duration_ms, $stats.vendored_skips)
}
