$tests = @(
    @{ name = "default (filter venv)"; msg = "busca archivos *.py en C:/AI_VAULT/00_identity" },
    @{ name = "explicit venv (include)"; msg = "busca archivos *.py en C:/AI_VAULT/00_identity incluyendo .venv" },
    @{ name = "no matches dir"; msg = "busca archivos *.xyz en C:/AI_VAULT/00_identity" }
)

foreach ($t in $tests) {
    Write-Host "===== $($t.name) ====="
    $body = @{ message = $t.msg; session_id = "bug7b_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
    $resp = "$($r.response)"
    $venvCount = ([regex]::Matches($resp, "\.venv")).Count
    $sitepkgCount = ([regex]::Matches($resp, "site-packages")).Count
    $omitidos = if ($resp -match "Omitidos (\d+)") { $matches[1] } else { "N/A" }
    Write-Host "  venv mentions: $venvCount | site-packages mentions: $sitepkgCount | omitidos: $omitidos"
    Write-Host "  first 200 chars: $($resp.Substring(0, [Math]::Min(200, $resp.Length)))"
    Write-Host ""
}
