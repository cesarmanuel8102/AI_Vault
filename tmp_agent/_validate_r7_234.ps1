# R7.2/3/4 E2E validator
$base = "http://127.0.0.1:8090"
$ok = 0; $fail = 0
$results = @()

function Test-Step($name, $cond, $detail) {
    if ($cond) {
        Write-Host "[PASS] $name" -ForegroundColor Green
        $script:ok++
        $script:results += "PASS: $name"
    } else {
        Write-Host "[FAIL] $name -> $detail" -ForegroundColor Red
        $script:fail++
        $script:results += "FAIL: $name -> $detail"
    }
}

# === R7.4: /brain/validators endpoint live ===
try {
    $v0 = Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 10
    Write-Host "Pre validators total_fires=$($v0.total_fires)"
    Write-Host "Live counters: $($v0.live_module_counters | ConvertTo-Json -Compress)"
    Test-Step "R7.4 endpoint /brain/validators reachable" $true ""
    Test-Step "R7.4 has merged + total_fires fields" ($v0.PSObject.Properties.Name -contains "merged" -and $v0.PSObject.Properties.Name -contains "total_fires") "missing fields"
} catch {
    Test-Step "R7.4 endpoint /brain/validators reachable" $false "err: $($_.Exception.Message)"
}

# === R7.2: introspection query → complex ===
# Send the same kind of query that broke 5/3.
$body = @{
    message = "revisa tu autonomia y autoconciensa actual y dime que ves"
    session_id = "r7_introspection"
} | ConvertTo-Json
Write-Host "Sending introspection query..."
try {
    $r = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 200
    Write-Host "Response (first 200ch): $($r.response.Substring(0,[Math]::Min(200,$r.response.Length)))"
    # Should NOT contain raw Python source (no leak)
    $hasLeak = ($r.response -match "class \w+:" -or $r.response -match "def __init__")
    Test-Step "R7.2 no source code leak in response" (-not $hasLeak) "leaked source: $($r.response.Substring(0,[Math]::Min(300,$r.response.Length)))"
} catch {
    Test-Step "R7.2 introspection completes" $false "err: $($_.Exception.Message)"
}

# Check log for "Task complexity: complex" line for that query
Start-Sleep 2
$latestLog = Get-ChildItem "C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$logContent = Get-Content $latestLog.FullName -Tail 200
$complexHit = $logContent | Select-String -Pattern "Task complexity: complex" -Quiet
Test-Step "R7.2 introspection classified complex" $complexHit "no 'Task complexity: complex' in latest log"

# === R7.3: pre-flight ctx routing on big prompt ===
$filler = ("Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " * 250)
$bigBody = @{
    message = "Resume esto en una palabra: $filler"
    session_id = "r7_preflight"
} | ConvertTo-Json -Compress
Write-Host "Sending oversized prompt..."
try {
    $r2 = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $bigBody -ContentType "application/json; charset=utf-8" -TimeoutSec 200
    Write-Host "Response sample: $($r2.response.Substring(0,[Math]::Min(120,$r2.response.Length)))"
} catch {
    Write-Host "Big request err: $($_.Exception.Message)"
}

Start-Sleep 2
$logContent2 = Get-Content $latestLog.FullName -Tail 300
$reroutehit = $logContent2 | Select-String -Pattern "Pre-flight ctx routing" -Quiet
Test-Step "R7.3 pre-flight ctx routing fired" $reroutehit "no 'Pre-flight ctx routing' in log"

# Check validator counter incremented
try {
    $v1 = Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 10
    Write-Host "Post validators: $($v1.merged | ConvertTo-Json -Compress)"
    $hasRoute = $v1.merged.PSObject.Properties.Name -contains "preflight_ctx_reroute"
    Test-Step "R7.3 counter preflight_ctx_reroute present" $hasRoute "counter missing"
} catch {
    Test-Step "R7.3 counter preflight_ctx_reroute present" $false "metrics err"
}

# === R7.4: validators persisted to disk after every chat (PERSIST_EVERY=1) ===
$diskFile = "C:\AI_VAULT\tmp_agent\state\brain_metrics\chat_metrics_latest.json"
$diskData = Get-Content $diskFile -Raw | ConvertFrom-Json
Write-Host "Disk validators: $($diskData.validators | ConvertTo-Json -Compress)"
$hasDiskCounter = $diskData.validators.PSObject.Properties.Name -contains "preflight_ctx_reroute" -or $diskData.validators.PSObject.Properties.Name -contains "ctx_too_tight_skip"
Test-Step "R7.4 validators persisted on disk after chats" $hasDiskCounter "no R7-era counters on disk"

Write-Host ""
Write-Host "=== R7.2/3/4 SUMMARY: $ok passed / $fail failed ==="
$results | ForEach-Object { Write-Host $_ }
