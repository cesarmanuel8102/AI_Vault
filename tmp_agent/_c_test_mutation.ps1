$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "C-Sprint: Code Mutation E2E Test" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

# Test 1: Direct mutation via endpoint
Write-Host ""
Write-Host "--- Test 1: Apply a trivial code mutation ---" -ForegroundColor Cyan

# Create a test file we can safely mutate
$testFile = "C:/AI_VAULT/tmp_agent/brain_v9/agent/_c_test_target.py"
$testContent = @"
# Test file for C-Sprint mutation testing
def example_function():
    result = 1 + 1  # OLD: this will be mutated
    return result

def another_function():
    return "hello"
"@
$testContent | Out-File -FilePath $testFile -Encoding utf8 -Force
Write-Host ("Created test file: {0}" -f $testFile)

# Apply a mutation
$mutationBody = @{
    file_path = $testFile
    edit_type = "replace"
    target = "result = 1 + 1  # OLD: this will be mutated"
    content = "result = 2 + 2  # MUTATED by C-Sprint test"
    description = "Test mutation: change arithmetic"
    allow_critical = $false
    monitor = $true
} | ConvertTo-Json -Compress

Write-Host "Sending mutation request..."
try {
    $resp = Invoke-RestMethod -Uri "$base/brain/mutations/test_apply" `
        -Method POST -Body $mutationBody -ContentType "application/json" -TimeoutSec 30
    Write-Host ("success={0}" -f $resp.success) -ForegroundColor Magenta
    Write-Host ("mutation_id={0}" -f $resp.mutation_id) -ForegroundColor Magenta
    Write-Host ("message={0}" -f $resp.message) -ForegroundColor Magenta
    $mutationId = $resp.mutation_id
} catch {
    Write-Host ("MUTATION FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
    $mutationId = $null
}

# Verify the file was mutated
Write-Host ""
Write-Host "--- Verify file content ---" -ForegroundColor Cyan
$newContent = Get-Content $testFile -Raw
if ($newContent -match "MUTATED by C-Sprint") {
    Write-Host "OK: File contains mutated content" -ForegroundColor Green
} else {
    Write-Host "FAIL: File does not contain mutated content" -ForegroundColor Red
}
Write-Host $newContent

# Check mutations list
Write-Host ""
Write-Host "--- Check mutations endpoint ---" -ForegroundColor Cyan
try {
    $mutations = Invoke-RestMethod -Uri "$base/brain/mutations" -TimeoutSec 5
    Write-Host ("count={0}" -f $mutations.count)
    foreach ($m in $mutations.mutations) {
        Write-Host ("  - {0} | {1} | rolled_back={2}" -f $m.id, $m.description, $m.rolled_back)
    }
} catch {
    Write-Host "Failed to get mutations" -ForegroundColor Red
}

# Check health gate
Write-Host ""
Write-Host "--- Check health gate status ---" -ForegroundColor Cyan
try {
    $gate = Invoke-RestMethod -Uri "$base/brain/health_gate/status" -TimeoutSec 5
    Write-Host ("active_sessions count: {0}" -f $gate.active_sessions.Count)
    foreach ($s in $gate.active_sessions) {
        Write-Host ("  - {0} | status={1} | elapsed={2:N1}s" -f $s.mutation_id, $s.status, $s.elapsed)
    }
} catch {
    Write-Host "Failed to get health gate status" -ForegroundColor Red
}

# Test 2: Rollback the mutation
if ($mutationId) {
    Write-Host ""
    Write-Host "--- Test 2: Rollback the mutation ---" -ForegroundColor Cyan
    try {
        $rollback = Invoke-RestMethod -Uri "$base/brain/mutations/$mutationId/rollback?reason=test_rollback" `
            -Method POST -TimeoutSec 10
        Write-Host ("rollback success={0}" -f $rollback.success) -ForegroundColor Magenta
        Write-Host ("message={0}" -f $rollback.message)
    } catch {
        Write-Host ("ROLLBACK FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
    }

    # Verify rollback
    Write-Host ""
    Write-Host "--- Verify rollback ---" -ForegroundColor Cyan
    $rolledContent = Get-Content $testFile -Raw
    if ($rolledContent -match "OLD: this will be mutated") {
        Write-Host "OK: File restored to original" -ForegroundColor Green
    } else {
        Write-Host "WARN: File not fully restored" -ForegroundColor Yellow
    }
    Write-Host $rolledContent
}

# Test 3: Check counters
Write-Host ""
Write-Host "--- Check relevant counters ---" -ForegroundColor Cyan
try {
    $c = (Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 5).live_module_counters
    $rel = $c.PSObject.Properties | Where-Object { $_.Name -match "mutation|reasoning|health_gate" }
    foreach ($r in $rel) { Write-Host ("  {0} = {1}" -f $r.Name, $r.Value) }
    if (-not $rel) { Write-Host "  (no relevant counters yet)" }
} catch {}

# Cleanup
Write-Host ""
Write-Host "--- Cleanup ---" -ForegroundColor Cyan
Remove-Item $testFile -Force -ErrorAction SilentlyContinue
Remove-Item "$testFile.bak.*" -Force -ErrorAction SilentlyContinue
Write-Host "Test file removed"
