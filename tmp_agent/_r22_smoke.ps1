$ErrorActionPreference = "Stop"
$queries = @(
    @{ id = "T8_repro"; q = "Hazme un mini reporte: (a) cuantos archivos hay en C:/AI_VAULT/tmp_agent/brain_v9/core, (b) cuantos hosts vivos en 192.168.1.0/29" },
    @{ id = "T2_repro"; q = "escanea mi red local 192.168.1.0/29" },
    @{ id = "files_count"; q = "cuantos archivos hay en C:/AI_VAULT/tmp_agent/brain_v9/agent" },
    @{ id = "scan_only"; q = "Escanea solo 192.168.1.250/30 y reporta puertos abiertos" }
)
$results = @()
foreach ($item in $queries) {
    Write-Host "===> [$($item.id)] $($item.q)" -ForegroundColor Cyan
    $body = @{ message = $item.q; session_id = "r22_$($item.id)" } | ConvertTo-Json -Compress
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 180
        $sw.Stop()
        $r = $resp.response; if ($null -eq $r) { $r = $resp.content }
        $route = $resp.route; if ($null -eq $route) { $route = $resp.model_used }
        $rprev = if ($r.Length -gt 400) { $r.Substring(0,400) + "..." } else { $r }
        Write-Host ("    route={0} dur={1}ms len={2}" -f $route, $sw.ElapsedMilliseconds, $r.Length) -ForegroundColor Yellow
        Write-Host "    --- response (preview) ---"
        Write-Host $rprev
        $results += @{ id = $item.id; q = $item.q; route = $route; dur_ms = $sw.ElapsedMilliseconds; resp = $r }
    } catch {
        $sw.Stop()
        Write-Host ("    ERROR: {0}" -f $_.Exception.Message) -ForegroundColor Red
        $results += @{ id = $item.id; q = $item.q; error = $_.Exception.Message; dur_ms = $sw.ElapsedMilliseconds }
    }
    Write-Host ""
}
$results | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 "_r22_smoke_results.json"
Write-Host "Saved _r22_smoke_results.json"
