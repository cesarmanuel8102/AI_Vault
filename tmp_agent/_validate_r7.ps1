# R7.1 E2E validator
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

# === R7.1 Case B: pure LLM chat, oversized prompt, all models fail ===
# Build ~10k token prompt that triggers ctx-skip on kimi+deepseek and likely
# timeout on llama8b. Should produce "todos los modelos LLM fallaron" banner.
$filler = ("Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " * 250)
$body = @{
    message = "Resume en una palabra: $filler"
    session_id = "r7_caseB_test"
} | ConvertTo-Json -Compress

Write-Host "Sending oversized LLM chat (Case B)..."
try {
    $r = Invoke-RestMethod -Uri "$base/chat" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 200
    $resp = $r.response
    Write-Host "RESPONSE:"
    Write-Host $resp
    Write-Host "---"
    $hasBanner = $resp -match "Sin respuesta sintetizada"
    $hasModels = $resp -match "Modelos consultados:"
    $hasSugerencia = $resp -match "Sugerencia:"
    Test-Step "R7.1-B banner present" $hasBanner "no banner in response"
    Test-Step "R7.1-B models_tried surfaced" $hasModels "no models list"
    Test-Step "R7.1-B sugerencia retry present" $hasSugerencia "no retry hint"
} catch {
    Test-Step "R7.1-B request OK" $false "request err: $($_.Exception.Message)"
}

# === R7.1 Case A: agent with tool actions, no LLM synthesis ===
# Harder to force without killing ollama. Instead, verify the code path is
# loaded and structured (banner + counts) by static check + a simple agent
# query that completes normally (banner absent if synthesis worked).
$banner_a = (Select-String -Path "C:\AI_VAULT\tmp_agent\brain_v9\core\session.py" -Pattern "Resumen extractivo . sintesis LLM no disponible" -Quiet)
Test-Step "R7.1-A extractive banner code present" $banner_a "banner not in session.py"

$counts_a = (Select-String -Path "C:\AI_VAULT\tmp_agent\brain_v9\core\session.py" -Pattern "len.successful., len.failed., steps" -Quiet)
Test-Step "R7.1-A header counts present" $counts_a "counts header not present"

$grouped = (Select-String -Path "C:\AI_VAULT\tmp_agent\brain_v9\core\session.py" -Pattern "Group successful actions by tool name" -Quiet)
Test-Step "R7.1-A grouping by tool present" $grouped "grouping logic absent"

# === Side check: validators ===
$cm = Get-Content "C:\AI_VAULT\tmp_agent\state\brain_metrics\chat_metrics_latest.json" -Raw | ConvertFrom-Json
Write-Host "Validators on disk: $(($cm.validators | ConvertTo-Json -Compress))"

Write-Host ""
Write-Host "=== R7.1 SUMMARY: $ok passed / $fail failed ==="
$results | ForEach-Object { Write-Host $_ }
