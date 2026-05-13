# Comprehensive battery test for R15+R16+R17+R18+R20
# Each test logs: question, route, success, latency, response (full + truncated for display)
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"
$out  = "C:/AI_VAULT/tmp_agent/_battery_results.json"
$logPath = "C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl"

# Capture event_log size BEFORE so we can diff the new events
$logSizeBefore = if (Test-Path $logPath) { (Get-Item $logPath).Length } else { 0 }

$tests = @(
    @{
        id="T1_R16_dir_read"
        sprint="R16"
        sid="battery_t1"
        question="Lee el archivo C:/AI_VAULT/tmp_agent/brain_v9 y dime el primer archivo que encuentres dentro"
        expected="should auto-list the directory and mention a file like main.py"
    },
    @{
        id="T2_R20_net_scan"
        sprint="R20"
        sid="battery_t2"
        question="Escanea mi red local 192.168.1.0/24 con timeout 0.3 y dime cuantos hosts vivos hay y cuales son"
        expected="should call scan_local_network with auto_chunk and return live hosts"
    },
    @{
        id="T3_R17_ps_var"
        sprint="R17"
        sid="battery_t3"
        question="Ejecuta este script PowerShell y dime el resultado: Write-Host (`$env:COMPUTERNAME + '_' + `$env:USERNAME)"
        expected="should use run_powershell (not cmd-mangled run_command) and return computer_user"
    },
    @{
        id="T4_R15_bad_path"
        sprint="R15"
        sid="battery_t4"
        question="Lee el archivo C:/no_existe_para_nada_xyz_12345.txt y dime que dice"
        expected="should get FileNotFoundError with hint, agent reports honestly that file not found"
    },
    @{
        id="T5_R16_complex"
        sprint="R16+R15"
        sid="battery_t5"
        question="Lista los archivos .py mas grandes en C:/AI_VAULT/tmp_agent/brain_v9/agent y dime su tamano"
        expected="should list dir contents and identify large .py files"
    },
    @{
        id="T6_R20_small_cidr"
        sprint="R20"
        sid="battery_t6"
        question="Escanea solo 192.168.1.250/30 y reporta puertos abiertos"
        expected="quick small scan, no chunking needed"
    },
    @{
        id="T7_R17_ps_file"
        sprint="R17"
        sid="battery_t7"
        question="Crea un script PowerShell que liste los procesos llamados python y ejecutalo"
        expected="should write .ps1 and call run_powershell with file_path"
    },
    @{
        id="T8_combined"
        sprint="R15+R16+R20"
        sid="battery_t8"
        question="Hazme un mini reporte: (a) cuantos archivos hay en C:/AI_VAULT/tmp_agent/brain_v9/core, (b) cuantos hosts vivos en 192.168.1.0/29"
        expected="multi-step: list_dir count + scan_local_network small CIDR"
    }
)

$results = @()
$total = $tests.Count
$idx = 0
foreach ($t in $tests) {
    $idx++
    Write-Host ("`n[{0}/{1}] {2}  ({3})" -f $idx, $total, $t.id, $t.sprint) -ForegroundColor Cyan
    Write-Host ("Q: {0}" -f $t.question) -ForegroundColor Gray

    $body = @{ message = $t.question; session_id = $t.sid } | ConvertTo-Json -Compress
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 180
        $sw.Stop()
        $resp = $r.response
        if (-not $resp) { $resp = $r.content }
        $route = $r.route
        $success = $r.success
        $model = $r.model_used
        $err = $r.error
    } catch {
        $sw.Stop()
        $resp = "REQUEST_ERROR: $($_.Exception.Message)"
        $route = "error"
        $success = $false
        $model = $null
        $err = $_.Exception.Message
    }
    $latency = [math]::Round($sw.Elapsed.TotalMilliseconds, 0)
    Write-Host ("R: route={0} success={1} model={2} dur={3}ms" -f $route, $success, $model, $latency) -ForegroundColor Yellow
    if ($resp) {
        $preview = $resp -replace "`n", " "
        if ($preview.Length -gt 280) { $preview = $preview.Substring(0,280) + "..." }
        Write-Host ("   {0}" -f $preview)
    }
    $results += [pscustomobject]@{
        id = $t.id
        sprint = $t.sprint
        question = $t.question
        expected = $t.expected
        sid = $t.sid
        route = $route
        success = $success
        model = $model
        latency_ms = $latency
        error = $err
        response = $resp
    }
}

# Tail event_log for chat.completed delta
Write-Host "`n=== Event log delta (chat.completed) ===" -ForegroundColor Cyan
$evCount = 0
if (Test-Path $logPath) {
    $stream = [System.IO.File]::OpenRead($logPath)
    $stream.Seek($logSizeBefore, [System.IO.SeekOrigin]::Begin) | Out-Null
    $reader = New-Object System.IO.StreamReader($stream)
    $newContent = $reader.ReadToEnd()
    $reader.Close()
    $stream.Close()
    $lines = $newContent -split "`n" | Where-Object { $_ -match "chat\.completed" }
    foreach ($ln in $lines) {
        try {
            $o = $ln | ConvertFrom-Json
            if ($o.payload.session_id -like "battery_*") {
                $evCount++
                Write-Host ("  {0}: route={1} ok={2} dur={3}ms resp_len={4}" -f `
                    $o.payload.session_id, $o.payload.route, $o.payload.success, `
                    $o.payload.duration_ms, $o.payload.response_len)
            }
        } catch {}
    }
}
Write-Host ("Battery events captured: {0}/{1}" -f $evCount, $total)

# Save full results
$results | ConvertTo-Json -Depth 6 | Set-Content -Path $out -Encoding UTF8
Write-Host ("`nFull results saved to: {0}" -f $out)
