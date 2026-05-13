$base = "http://127.0.0.1:8090"

# Queries que forzan razonamiento LLM + tools (no fastpath)
$queries = @(
    "analiza el archivo C:/AI_VAULT/tmp_agent/brain_v9/main.py y dime cuantas funciones tiene",
    "busca en el codigo Python instancias de la palabra TODO en C:/AI_VAULT/tmp_agent/brain_v9",
    "lee el archivo C:/AI_VAULT/tmp_agent/_r14_smoke.ps1 y dime que hace",
    "que puertos estan abiertos en este servidor"
)
foreach ($q in $queries) {
    $body = @{ message = $q; session_id = "r14b_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 180
        $modelUsed = $r.model_used
        Write-Host "  [$modelUsed] $q"
    } catch {
        Write-Host "  [TIMEOUT] $q"
    }
}

Write-Host ""
Write-Host "===== /tools/coverage post-loop ====="
$r1 = Invoke-RestMethod -Uri "$base/tools/coverage" -Method Get -TimeoutSec 10
$r1.totals | Format-List
Write-Host "tools tracked:"
$r1.tools.PSObject.Properties | Sort-Object { $_.Value.invocations } -Descending | ForEach-Object {
    $s = $_.Value
    Write-Host ("  - {0,-30} inv={1} succ={2} fail={3} schema={4} trunc={5} vskip={6} avg_ms={7,8} max_ms={8,8}" -f $_.Name, $s.invocations, $s.successes, $s.failures, $s.schema_violations, $s.truncations, $s.vendored_skips, $s.avg_duration_ms, $s.max_duration_ms)
}
Write-Host ""
Write-Host "top_failing detail:"
$r1.top_failing | ConvertTo-Json -Depth 4
