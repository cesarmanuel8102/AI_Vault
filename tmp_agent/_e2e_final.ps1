$ErrorActionPreference = 'Continue'
$results = @{}
$base = 'http://127.0.0.1:8090'

function Send-Chat($name, $msg, $timeoutSec = 240) {
    $body = @{ message = $msg; session_id = "e2e_$name" } | ConvertTo-Json
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod -Uri "$base/chat" -Method POST -Body $body -ContentType 'application/json' -TimeoutSec $timeoutSec
        $sw.Stop()
        return @{ name=$name; ok=$true; ms=$sw.ElapsedMilliseconds; reply=$r.response; meta=$r }
    } catch {
        $sw.Stop()
        return @{ name=$name; ok=$false; ms=$sw.ElapsedMilliseconds; error=$_.Exception.Message }
    }
}

Write-Host "=== T1 R22+R25 scan red ==="
$t1 = Send-Chat 't1_scan' 'escanea mi red local 192.168.1.0/24 y dime cuantos hosts hay'
Write-Host "  ok=$($t1.ok) ms=$($t1.ms)"
Write-Host "  reply: $($t1.reply.Substring(0, [Math]::Min(200,$t1.reply.Length)))"

Write-Host "`n=== T2 R22+R26 nmap auto-fallback ==="
$t2 = Send-Chat 't2_nmap' 'usa nmap para escanear 192.168.1.0/24 y dime cuantos hosts hay'
Write-Host "  ok=$($t2.ok) ms=$($t2.ms)"
Write-Host "  reply: $($t2.reply.Substring(0, [Math]::Min(200,$t2.reply.Length)))"

Write-Host "`n=== T3 R24 PowerShell `$ retry ==="
$t3 = Send-Chat 't3_psdollar' 'ejecuta este comando powershell: Get-Process | Where-Object {$_.CPU -gt 10} | Select-Object -First 3 Name'
Write-Host "  ok=$($t3.ok) ms=$($t3.ms)"
Write-Host "  reply: $($t3.reply.Substring(0, [Math]::Min(200,$t3.reply.Length)))"

Write-Host "`n=== T4 ghost-completion fallback ==="
$t4 = Send-Chat 't4_ghost' 'que hora es ahora mismo en mi sistema'
Write-Host "  ok=$($t4.ok) ms=$($t4.ms)"
Write-Host "  reply: $($t4.reply.Substring(0, [Math]::Min(200,$t4.reply.Length)))"

Write-Host "`n=== T5 R27 settings now active ==="
$s = Invoke-RestMethod -Uri "$base/upgrade/settings" -Method GET
Write-Host "  self_dev_enabled=$($s.self_dev_enabled) require_approval=$($s.self_dev_require_approval)"

$summary = @{
    t1=@{ok=$t1.ok; ms=$t1.ms; reply_len=$t1.reply.Length}
    t2=@{ok=$t2.ok; ms=$t2.ms; reply_len=$t2.reply.Length}
    t3=@{ok=$t3.ok; ms=$t3.ms; reply_len=$t3.reply.Length}
    t4=@{ok=$t4.ok; ms=$t4.ms; reply_len=$t4.reply.Length}
    settings=@{enabled=$s.self_dev_enabled; require_approval=$s.self_dev_require_approval}
}
$summary | ConvertTo-Json -Depth 5 | Set-Content C:/AI_VAULT/tmp_agent/_e2e_final_summary.json
@{t1=$t1; t2=$t2; t3=$t3; t4=$t4} | ConvertTo-Json -Depth 5 | Set-Content C:/AI_VAULT/tmp_agent/_e2e_final_full.json
Write-Host "`nSUMMARY:"
$summary | ConvertTo-Json -Depth 5
