$ErrorActionPreference = "Stop"
$queries = @(
    "has estado mejorandote ultimamente?",
    "cuanto has estado trabajando ultimmente para eso?",
    "que has hecho ultimamente?",
    "que tools fallaron recientes?"
)
$results = @()
foreach ($q in $queries) {
    Write-Host "===> Q: $q" -ForegroundColor Cyan
    $body = @{ message = $q; session_id = "r21_smoke" } | ConvertTo-Json -Compress
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
        $sw.Stop()
        $r = $resp.response
        if ($null -eq $r) { $r = $resp.content }
        $route = $resp.route
        if ($null -eq $route) { $route = $resp.model_used }
        Write-Host ("    route={0} dur={1}ms len={2}" -f $route, $sw.ElapsedMilliseconds, $r.Length) -ForegroundColor Yellow
        Write-Host "    --- response ---"
        Write-Host $r
        $results += @{ q = $q; route = $route; dur_ms = $sw.ElapsedMilliseconds; resp = $r }
    } catch {
        $sw.Stop()
        Write-Host ("    ERROR: {0}" -f $_.Exception.Message) -ForegroundColor Red
        $results += @{ q = $q; error = $_.Exception.Message }
    }
    Write-Host ""
}
$results | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 "_r21_smoke_results.json"
Write-Host "Saved _r21_smoke_results.json"
