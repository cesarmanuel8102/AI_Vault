import io, sys, json, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")
from brain_v9.autonomy.chat_excellence_patcher import apply_proposal, rollback_proposal
from pathlib import Path

# Make a safety copy of core/llm.py before any test (paranoia)
LLM = "C:/AI_VAULT/tmp_agent/brain_v9/core/llm.py"
SAFE = LLM + ".pretest_safety"
shutil.copy2(LLM, SAFE)
print(f"safety copy made: {SAFE}")

# pid from previous test
pid = "ce_prop_20260504_133441"
print(f"\n=== APPLY {pid} ===")
result = apply_proposal(pid, by="test_runner", note="r10.2b validation")
print(json.dumps({k: v for k, v in result.items() if k != "diff"}, indent=2, default=str))

# verify file changed
content = Path(LLM).read_text(encoding="utf-8")
assert "_CB_FAIL_THRESHOLD = 5" in content, "expected _CB_FAIL_THRESHOLD=5 after apply"
assert "_CB_COOLDOWN_S = 60" in content,    "expected _CB_COOLDOWN_S=60 after apply"
print("OK: file actually modified")

# verify py_compile ok
import py_compile
py_compile.compile(LLM, doraise=True)
print("OK: py_compile passes")

# Now rollback
print(f"\n=== ROLLBACK {pid} ===")
rb = rollback_proposal(pid, reason="r10.2b validation cleanup")
print(json.dumps(rb, indent=2, default=str))

content2 = Path(LLM).read_text(encoding="utf-8")
assert "_CB_FAIL_THRESHOLD = 2" in content2, "expected rollback to _CB_FAIL_THRESHOLD=2"
assert "_CB_COOLDOWN_S = 180" in content2,   "expected rollback to _CB_COOLDOWN_S=180"
print("OK: file rolled back to original")

# diff vs safety copy
orig = Path(SAFE).read_text(encoding="utf-8")
if orig == content2:
    print("OK: file IDENTICAL to pre-test safety copy")
else:
    print("WARN: file differs from safety copy - investigate!")

# cleanup safety copy and backup file
Path(SAFE).unlink()
print("safety copy removed")
