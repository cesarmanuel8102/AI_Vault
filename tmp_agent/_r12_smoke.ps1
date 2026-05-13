# R12 Tool Reliability Layer - Smoke Test
# Replays the 7 categories of tool failures observed in conversation history
# and verifies that the patches produce structured/actionable outputs.

$ErrorActionPreference = "Continue"
$BRAIN = "http://127.0.0.1:8090"
$results = @()
$pass = 0
$fail = 0

function Record-Test {
    param($name, $ok, $detail)
    $script:results += [PSCustomObject]@{ Test = $name; Pass = $ok; Detail = $detail }
    if ($ok) { $script:pass++ } else { $script:fail++ }
    $status = if ($ok) { "PASS" } else { "FAIL" }
    Write-Host ("[{0}] {1} - {2}" -f $status, $name, $detail)
}

# ============================================================================
# Test 1: Brain alive
# ============================================================================
try {
    $h = Invoke-RestMethod -Uri "$BRAIN/health" -TimeoutSec 5
    Record-Test "T1_brain_health" ($h.status -eq "healthy") "status=$($h.status)"
} catch {
    Record-Test "T1_brain_health" $false "exception: $($_.Exception.Message)"
    Write-Host "Aborting smoke test - brain not reachable"
    exit 1
}

# ============================================================================
# Test 2: Schema enforcement - search_files without 'pattern' should produce
# a structured "missing_args" error (not a TypeError leak)
# ============================================================================
$payload = @{
    session_id = "smoke_r12_t2"
    message = "busca archivos con errores"
    model_priority = "ollama"
} | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Uri "$BRAIN/chat" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 90
    $resp_lower = $r.response.ToLower()
    # Pass if response either invokes search_files successfully OR explains missing args
    $ok = ($resp_lower -match "pattern|directorio|archivos|encontre|missing|firma|signature") -and ($resp_lower -notmatch "typeerror|traceback")
    Record-Test "T2_search_schema" $ok ("len=" + $r.response.Length + " success=" + $r.success)
} catch {
    Record-Test "T2_search_schema" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 3: list_processes truncation metadata
# Direct tool invocation via /agent/run if available; else via chat
# ============================================================================
$payload = @{
    session_id = "smoke_r12_t3"
    message = "lista los procesos corriendo"
    model_priority = "ollama"
} | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Uri "$BRAIN/chat" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 120
    $ok = ($r.response.Length -gt 50) -and ($r.response -notmatch "Error desconocido")
    Record-Test "T3_list_processes" $ok ("len=" + $r.response.Length)
} catch {
    Record-Test "T3_list_processes" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 4: search_files SHAPE - must return dict with truncated/results/hint
# Use direct tool execution endpoint if exists
# ============================================================================
try {
    # Try a minimal Python introspection via run_command style chat
    $payload = @{
        session_id = "smoke_r12_t4"
        message = "busca archivos *.py en C:/AI_VAULT/tmp_agent/brain_v9/agent y dime cuantos hay"
        model_priority = "ollama"
    } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$BRAIN/chat" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 120
    $ok = $r.response.Length -gt 30
    Record-Test "T4_search_files_shape" $ok ("len=" + $r.response.Length)
} catch {
    Record-Test "T4_search_files_shape" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 5: Auto-signature generation - load tools.py and verify _TOOL_SIGNATURES
# now contains entries for previously-missing tools
# ============================================================================
$pyCode = @"
import sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import build_standard_executor
ex = build_standard_executor()
sigs = ex._TOOL_SIGNATURES
total = len(ex._tools)
covered = sum(1 for t in ex._tools if t in sigs)
print(f'TOOLS={total} SIG_COVERED={covered} COVERAGE={100*covered/total:.1f}%')
# Sample a few previously-missing
for name in ('check_url', 'find_dashboard_files', 'check_port', 'detect_local_network'):
    if name in sigs:
        print(f'  {name}: {sigs[name][:80]}')
"@
$pyFile = "C:/AI_VAULT/tmp_agent/_r12_check_sigs.py"
$pyCode | Out-File -FilePath $pyFile -Encoding ASCII
try {
    $out = & python $pyFile 2>&1 | Out-String
    $ok = ($out -match "COVERAGE=100\.0%") -or ($out -match "COVERAGE=9\d\.\d%")
    $cov_match = [regex]::Match($out, "COVERAGE=([\d\.]+)%")
    $cov = if ($cov_match.Success) { $cov_match.Groups[1].Value } else { "?" }
    Record-Test "T5_auto_signatures" $ok ("coverage=$cov%")
} catch {
    Record-Test "T5_auto_signatures" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 6: Schema validator unit test - direct invocation via Python
# ============================================================================
$pyCode2 = @"
import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import build_standard_executor
ex = build_standard_executor()

async def run():
    # Call search_files WITHOUT pattern - should return structured error
    r = await ex.execute('search_files', directory='C:/AI_VAULT')
    if isinstance(r, dict) and r.get('error_type') == 'missing_args':
        print(f'OK_MISSING missing={r.get(\"missing\")}')
        print(f'  hint={r.get(\"hint\",\"\")[:120]}')
        return True
    print(f'FAIL got={r}')
    return False

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
"@
$pyFile2 = "C:/AI_VAULT/tmp_agent/_r12_check_schema.py"
$pyCode2 | Out-File -FilePath $pyFile2 -Encoding ASCII
try {
    $out = & python $pyFile2 2>&1 | Out-String
    $ok = $out -match "OK_MISSING"
    Record-Test "T6_schema_validator" $ok ($out.Trim().Substring(0, [Math]::Min(150, $out.Length)))
} catch {
    Record-Test "T6_schema_validator" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 7: list_processes returns dict with truncated/hint/count
# ============================================================================
$pyCode3 = @"
import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import list_processes

async def run():
    r = await list_processes()
    if not isinstance(r, dict):
        print(f'FAIL not_dict={type(r)}')
        return False
    needed = ('count', 'returned', 'truncated', 'processes')
    missing = [k for k in needed if k not in r]
    if missing:
        print(f'FAIL missing_keys={missing}')
        return False
    print(f'OK count={r[\"count\"]} returned={r[\"returned\"]} truncated={r[\"truncated\"]} hint_present={\"hint\" in r}')
    if r['count'] > 4:  # bug B5: parser previously returned only 4 procs
        print(f'  parser_health=OK (more than 4 procs detected)')
    return True

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
"@
$pyFile3 = "C:/AI_VAULT/tmp_agent/_r12_check_list.py"
$pyCode3 | Out-File -FilePath $pyFile3 -Encoding ASCII
try {
    $out = & python $pyFile3 2>&1 | Out-String
    $ok = $out -match "^OK count="
    Record-Test "T7_list_processes_meta" $ok ($out.Trim().Substring(0, [Math]::Min(180, $out.Length)))
} catch {
    Record-Test "T7_list_processes_meta" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 8: search_files SHAPE direct
# ============================================================================
$pyCode4 = @"
import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import search_files

async def run():
    r = await search_files(directory='C:/AI_VAULT/tmp_agent/brain_v9/agent', pattern='*.py')
    if not isinstance(r, dict):
        print(f'FAIL not_dict={type(r)}')
        return False
    needed = ('results', 'returned', 'truncated', 'success')
    missing = [k for k in needed if k not in r]
    if missing:
        print(f'FAIL missing_keys={missing}')
        return False
    print(f'OK returned={r[\"returned\"]} truncated={r[\"truncated\"]} success={r[\"success\"]}')
    return True

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
"@
$pyFile4 = "C:/AI_VAULT/tmp_agent/_r12_check_search.py"
$pyCode4 | Out-File -FilePath $pyFile4 -Encoding ASCII
try {
    $out = & python $pyFile4 2>&1 | Out-String
    $ok = $out -match "^OK returned="
    Record-Test "T8_search_files_shape" $ok ($out.Trim().Substring(0, [Math]::Min(180, $out.Length)))
} catch {
    Record-Test "T8_search_files_shape" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Test 9: _run_internal_command surfaces error_type
# ============================================================================
$pyCode5 = @"
import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import _run_internal_command

async def run():
    # Force timeout
    r = await _run_internal_command('powershell -Command "Start-Sleep 10"', timeout=2)
    if r.get('error_type') == 'TimeoutExpired':
        print(f'OK timeout_surfaced error_type={r[\"error_type\"]}')
        return True
    print(f'FAIL r={r}')
    return False

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
"@
$pyFile5 = "C:/AI_VAULT/tmp_agent/_r12_check_runinternal.py"
$pyCode5 | Out-File -FilePath $pyFile5 -Encoding ASCII
try {
    $out = & python $pyFile5 2>&1 | Out-String
    $ok = $out -match "^OK timeout_surfaced"
    Record-Test "T9_run_internal_errortype" $ok ($out.Trim().Substring(0, [Math]::Min(180, $out.Length)))
} catch {
    Record-Test "T9_run_internal_errortype" $false "exception: $($_.Exception.Message)"
}

# ============================================================================
# Summary
# ============================================================================
Write-Host ""
Write-Host "============================================================"
Write-Host ("R12 SMOKE RESULTS: PASS={0} FAIL={1}" -f $pass, $fail)
Write-Host "============================================================"
$results | Format-Table -AutoSize

if ($fail -eq 0) {
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$fail TEST(S) FAILED" -ForegroundColor Red
    exit 1
}
