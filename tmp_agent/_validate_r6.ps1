# R6 E2E Validator
$base = "http://127.0.0.1:8090"
$ok = 0; $fail = 0
$results = @()

function Test-Step($name, $ok_cond, $detail) {
    if ($ok_cond) {
        Write-Host "[PASS] $name" -ForegroundColor Green
        $script:ok++
        $script:results += "PASS: $name"
    } else {
        Write-Host "[FAIL] $name -> $detail" -ForegroundColor Red
        $script:fail++
        $script:results += "FAIL: $name -> $detail"
    }
}

# Snapshot validators counters before
$pre = $null
try {
    $m = Invoke-RestMethod -Uri "$base/metrics/chat" -TimeoutSec 10
    $pre = $m
} catch {
    Write-Host "metrics/chat unavailable: $($_.Exception.Message)"
}
$pre_ctx_skip = 0
$pre_capped = 0
if ($pre -and $pre.validators) {
    if ($pre.validators.ctx_too_tight_skip) { $pre_ctx_skip = $pre.validators.ctx_too_tight_skip }
    if ($pre.validators.num_predict_capped) { $pre_capped = $pre.validators.num_predict_capped }
}
Write-Host "Pre counters: ctx_too_tight_skip=$pre_ctx_skip num_predict_capped=$pre_capped"

# === R6.3: UTF-8 sanity ===
# Send a query that should produce Spanish accents and verify no mojibake.
$body = @{
    message = "Responde EXACTAMENTE con esta frase y nada mas: 'Operacion aritmetica basica con tildes: cancion, accion, peticion.'"
    session_id = "r6_utf8_test"
} | ConvertTo-Json
try {
    $resp = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 90
    $r = $resp.response
    Write-Host "R6.3 response: $($r.Substring(0,[Math]::Min(200,$r.Length)))"
    # Check no mojibake patterns (e.g., letterDigit substitutions)
    $mojibake = ($r -match "[a-z]A[0-9][a-z]") -or ($r -match "A�")
    Test-Step "R6.3 no_mojibake" (-not $mojibake) "found mojibake in: $r"
} catch {
    Test-Step "R6.3 no_mojibake" $false "request failed: $($_.Exception.Message)"
}

# === R6.1: large prompt should trigger Ctx-skip on kimi_cloud ===
# Build a ~5500-token prompt by repeating filler (>~22000 chars).
$filler = ("Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " * 200)
$bigBody = @{
    message = "Resume en una sola palabra el tema principal del siguiente texto: $filler"
    session_id = "r6_ctx_skip_test"
} | ConvertTo-Json -Compress
try {
    $r2 = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $bigBody -ContentType "application/json; charset=utf-8" -TimeoutSec 180
    Write-Host "R6.1 response sample: $($r2.response.Substring(0,[Math]::Min(120,$r2.response.Length)))"
} catch {
    Write-Host "R6.1 chat err: $($_.Exception.Message)"
}

Start-Sleep 3
# Check counter delta
try {
    $m2 = Invoke-RestMethod -Uri "$base/metrics/chat" -TimeoutSec 10
    $post_ctx_skip = 0
    if ($m2.validators -and $m2.validators.ctx_too_tight_skip) { $post_ctx_skip = $m2.validators.ctx_too_tight_skip }
    Write-Host "Post counters: ctx_too_tight_skip=$post_ctx_skip"
    Test-Step "R6.1 ctx_too_tight_skip incremented" ($post_ctx_skip -gt $pre_ctx_skip) "delta=0 (pre=$pre_ctx_skip post=$post_ctx_skip)"
} catch {
    Test-Step "R6.1 ctx_too_tight_skip incremented" $false "metrics unavailable"
}

# === R6.2: banner should appear when LLM synthesis fails ===
# We can't easily kill ollama; instead grep recent stderr log for banner string
# AND verify the banner string exists in code path. The real proof comes when
# user hits a degraded path. For now, check the code is loaded.
$banner_code_exists = (Select-String -Path "C:\AI_VAULT\tmp_agent\brain_v9\core\session.py" -Pattern "Resumen operacional . sintesis LLM no disponible" -Quiet)
Test-Step "R6.2 banner string present in code" $banner_code_exists "banner not found in session.py"

# Also verify _format_tool_result truncates code-like content fields.
$truncate_exists = (Select-String -Path "C:\AI_VAULT\tmp_agent\brain_v9\core\session.py" -Pattern "code_field truncado" -Quiet)
Test-Step "R6.2 truncate code-field rule present" $truncate_exists "rule not found"

Write-Host ""
Write-Host "=== R6 SUMMARY: $ok passed / $fail failed ==="
$results | ForEach-Object { Write-Host $_ }
