# R8 E2E validator — checks endpoint shape + makes a chat to populate latency buffers
$ErrorActionPreference = 'Continue'
$results = @()

function Test-Step($name, $block) {
    try {
        $r = & $block
        $results += [pscustomobject]@{ Step=$name; Status='OK'; Detail=$r }
        Write-Host "[OK]   $name -> $r"
    } catch {
        $results += [pscustomobject]@{ Step=$name; Status='FAIL'; Detail=$_.Exception.Message }
        Write-Host "[FAIL] $name -> $($_.Exception.Message)"
    }
}

Write-Host "=== R8 Validation ==="

Test-Step "1. /health responds" {
    $h = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 10
    "status=$($h.status)"
}

Test-Step "2. /brain/validators returns expected keys" {
    $v = Invoke-RestMethod -Uri http://127.0.0.1:8090/brain/validators -TimeoutSec 10
    $keys = ($v | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name) -join ','
    $missing = @()
    foreach ($k in 'live_module_counters','chat_metrics_validators','merged','total_fires','llm_latency','chain_health') {
        if (-not ($v.PSObject.Properties.Name -contains $k)) { $missing += $k }
    }
    if ($missing.Count -gt 0) { throw "Missing keys: $($missing -join ',')" }
    "keys=$keys"
}

Test-Step "3. POST /chat to generate latency sample" {
    $body = @{ message='Hola, prueba breve para R8'; session_id='r8_validate' } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180
    $resp = if ($r.response) { $r.response.Substring(0, [Math]::Min(80, $r.response.Length)) } else { '(no response)' }
    "len=$($r.response.Length) preview='$resp...'"
}

Test-Step "4. /brain/validators now has llm_latency populated" {
    Start-Sleep 2
    $v = Invoke-RestMethod -Uri http://127.0.0.1:8090/brain/validators -TimeoutSec 10
    $models = ($v.llm_latency.PSObject.Properties.Name | Where-Object { $_ -ne '_error' }) -join ','
    if (-not $models) { throw 'llm_latency vacio tras chat' }
    "models=$models"
}

Test-Step "5. /brain/validators chain_health populated" {
    $v = Invoke-RestMethod -Uri http://127.0.0.1:8090/brain/validators -TimeoutSec 10
    $chains = ($v.chain_health.PSObject.Properties.Name | Where-Object { $_ -ne '_error' }) -join ','
    if (-not $chains) { throw 'chain_health vacio' }
    "chains=$chains"
}

Test-Step "6. Dashboard HTML contains R8.4 panel" {
    $html = Invoke-WebRequest -Uri http://127.0.0.1:8090/dashboard -UseBasicParsing -TimeoutSec 10
    if ($html.Content -notmatch 'brain-validators-panel') { throw 'Panel id missing' }
    if ($html.Content -notmatch 'refreshBrainValidators') { throw 'JS func missing' }
    'panel+JS present'
}

Test-Step "7. Dashboard panel renders latency samples (poll fn)" {
    $v = Invoke-RestMethod -Uri http://127.0.0.1:8090/brain/validators -TimeoutSec 10
    $first = $v.llm_latency.PSObject.Properties | Where-Object { $_.Name -ne '_error' } | Select-Object -First 1
    if ($null -eq $first) { throw 'no latency samples' }
    $p = $first.Value
    "model=$($first.Name) count=$($p.count) p50=$($p.p50)s p95=$($p.p95)s"
}

Write-Host ""
Write-Host "=== Summary ==="
$ok = ($results | Where-Object { $_.Status -eq 'OK' }).Count
$fail = ($results | Where-Object { $_.Status -eq 'FAIL' }).Count
Write-Host "OK:$ok FAIL:$fail"
$results | Format-Table -AutoSize
