$ErrorActionPreference = 'Continue'
$base = 'http://127.0.0.1:8090'

function Send-Chat($name, $msg, $timeoutSec = 240) {
    $body = @{ message = $msg; session_id = "e2e2_$name" } | ConvertTo-Json
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod -Uri "$base/chat" -Method POST -Body $body -ContentType 'application/json' -TimeoutSec $timeoutSec
        $sw.Stop()
        $reply = if ($r.response) { $r.response } else { '' }
        return @{ name=$name; ok=$true; ms=$sw.ElapsedMilliseconds; reply=$reply; raw=$r }
    } catch {
        $sw.Stop()
        return @{ name=$name; ok=$false; ms=$sw.ElapsedMilliseconds; error=$_.Exception.Message }
    }
}

Write-Host "`n=== T1 R28 fast-synth: scan red ==="
$t1 = Send-Chat 't1_scan' 'escanea mi red local 192.168.1.0/24 y dime cuantos hosts hay'
Write-Host "  ms=$($t1.ms) reply_len=$($t1.reply.Length)"
if ($t1.reply) { Write-Host "  preview: $($t1.reply.Substring(0,[Math]::Min(250,$t1.reply.Length)))" }

Write-Host "`n=== T2 R26 + R28 fast-synth: nmap fallback ==="
$t2 = Send-Chat 't2_nmap' 'usa nmap para escanear 192.168.1.0/24 y dime cuantos hosts hay'
Write-Host "  ms=$($t2.ms) reply_len=$($t2.reply.Length)"
if ($t2.reply) { Write-Host "  preview: $($t2.reply.Substring(0,[Math]::Min(250,$t2.reply.Length)))" }

Write-Host "`n=== T3 R24v2 auto-rewrite PowerShell `$ ==="
$t3 = Send-Chat 't3_psdollar' 'ejecuta este comando powershell: Get-Process | Where-Object {$_.CPU -gt 10} | Select-Object -First 3 Name'
Write-Host "  ms=$($t3.ms) reply_len=$($t3.reply.Length)"
if ($t3.reply) { Write-Host "  preview: $($t3.reply.Substring(0,[Math]::Min(300,$t3.reply.Length)))" }

Write-Host "`n=== T4 fastpath: hora ==="
$t4 = Send-Chat 't4_time' 'que hora es ahora mismo en mi sistema'
Write-Host "  ms=$($t4.ms) reply_len=$($t4.reply.Length)"
if ($t4.reply) { Write-Host "  preview: $($t4.reply.Substring(0,[Math]::Min(150,$t4.reply.Length)))" }

Write-Host "`n=== T5 verify relevance: count intent ==="
$t5 = Send-Chat 't5_count' 'cuantos puertos TCP estan abiertos en 127.0.0.1 entre 8000 y 8100'
Write-Host "  ms=$($t5.ms) reply_len=$($t5.reply.Length)"
if ($t5.reply) { Write-Host "  preview: $($t5.reply.Substring(0,[Math]::Min(250,$t5.reply.Length)))" }

Write-Host "`n=== T6 R27 deep test: capability remediate install ==="
try {
    $payload = @{ requested_tool='httpx'; allow_install=$true } | ConvertTo-Json
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $r6 = Invoke-RestMethod -Uri "$base/upgrade/capabilities/remediate" -Method POST -Body $payload -ContentType 'application/json' -TimeoutSec 180
    $sw.Stop()
    Write-Host "  ms=$($sw.ElapsedMilliseconds)"
    Write-Host "  result: $($r6 | ConvertTo-Json -Depth 4 -Compress)"
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)"
}

Write-Host "`n=== Settings final ==="
$s = Invoke-RestMethod -Uri "$base/upgrade/settings" -Method GET
Write-Host "  enabled=$($s.self_dev_enabled) approval=$($s.self_dev_require_approval) max_risk=$($s.self_dev_max_risk)"

$summary = @{
    t1_scan_fast=@{ms=$t1.ms; len=$t1.reply.Length; ok=$t1.ok}
    t2_nmap_fast=@{ms=$t2.ms; len=$t2.reply.Length; ok=$t2.ok}
    t3_psdollar=@{ms=$t3.ms; len=$t3.reply.Length; ok=$t3.ok}
    t4_time=@{ms=$t4.ms; len=$t4.reply.Length; ok=$t4.ok}
    t5_count=@{ms=$t5.ms; len=$t5.reply.Length; ok=$t5.ok}
}
$summary | ConvertTo-Json -Depth 5 | Set-Content C:/AI_VAULT/tmp_agent/_e2e_v2_summary.json
@{t1=$t1; t2=$t2; t3=$t3; t4=$t4; t5=$t5} | ConvertTo-Json -Depth 6 | Set-Content C:/AI_VAULT/tmp_agent/_e2e_v2_full.json
Write-Host "`nSUMMARY:"
$summary | ConvertTo-Json -Depth 5
