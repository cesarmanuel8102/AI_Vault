$ErrorActionPreference = 'Stop'
python -m py_compile C:/AI_VAULT/tmp_agent/brain_v9/autonomy/chat_excellence_patcher.py
if ($LASTEXITCODE -eq 0) { Write-Host "[compile] OK" -ForegroundColor Green } else { Write-Host "[compile] FAIL exit=$LASTEXITCODE" -ForegroundColor Red; exit 1 }

# Quick regex / extractor smoke test
$py = @'
import sys
sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")
from brain_v9.autonomy.chat_excellence_patcher import (
    extract_constant_changes, _PATCHABLE_FILES, _is_forbidden,
    _resolve_patchable_file, _find_constant_line,
)

print("[whitelist]", sorted(_PATCHABLE_FILES))

# 1) Old style (underscore prefix) still works
c = extract_constant_changes("_CB_FAIL_THRESHOLD: elevar de 2 a 5")
assert c == [{"name":"_CB_FAIL_THRESHOLD","old_value":2,"new_value":5}], f"old style fail: {c}"
print("[regex] old underscore-prefix style OK")

# 2) New ALL_CAPS without prefix works
c = extract_constant_changes("Subir MIN_IMPACT_SCORE de 7 a 8 para reducir ruido")
assert c == [{"name":"MIN_IMPACT_SCORE","old_value":7,"new_value":8}], f"new style fail: {c}"
print("[regex] new no-prefix style OK")

# 3) Common words must NOT match
c = extract_constant_changes("Set MAX to 10 and TRUE to 1")
assert c == [], f"false positive: {c}"
print("[regex] common-word false-positive guard OK")

# 4) Per-file forbidden
assert _is_forbidden("MAX_PROPOSALS_KEEP", "autonomy/chat_excellence_executor.py")
assert not _is_forbidden("MAX_PROPOSALS_KEEP", "core/llm.py")  # not forbidden in llm.py
assert _is_forbidden("_PERSIST_EVERY", "core/llm.py")          # global forbidden
print("[forbidden] per-file dispatch OK")

# 5) New whitelist files resolve
assert _resolve_patchable_file("autonomy/chat_excellence_executor.py") is not None
assert _resolve_patchable_file("autonomy/proactive_scheduler.py") is not None
assert _resolve_patchable_file("core/llm.py") is not None
assert _resolve_patchable_file("agent/tools.py") is None  # not in whitelist
print("[whitelist] resolve OK")

# 6) find_constant_line on new files (real on-disk)
exec_p = _resolve_patchable_file("autonomy/chat_excellence_executor.py")
content = exec_p.read_text(encoding="utf-8")
loc = _find_constant_line(content, "MIN_IMPACT_SCORE")
assert loc is not None, "MIN_IMPACT_SCORE not found"
print(f"[find_const] MIN_IMPACT_SCORE at line {loc[0]+1} value={loc[2]}")

sched_p = _resolve_patchable_file("autonomy/proactive_scheduler.py")
content = sched_p.read_text(encoding="utf-8")
loc = _find_constant_line(content, "CHECK_INTERVAL")
assert loc is not None, "CHECK_INTERVAL not found"
print(f"[find_const] CHECK_INTERVAL at line {loc[0]+1} value={loc[2]}")

print("ALL UNIT CHECKS PASSED")
'@
$py | Out-File -Encoding utf8 C:/AI_VAULT/tmp_agent/_r10_6_unit.py
python C:/AI_VAULT/tmp_agent/_r10_6_unit.py
if ($LASTEXITCODE -ne 0) { Write-Host "[unit] FAIL" -ForegroundColor Red; exit 1 }
Write-Host "[unit] OK" -ForegroundColor Green
