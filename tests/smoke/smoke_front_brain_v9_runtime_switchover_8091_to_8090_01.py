import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"tmp_agent"/"front_brain_v9_runtime_switchover_8091_to_8090_01"

def _json(p): return json.loads(p.read_text(encoding="utf-8-sig"))
def _git(args): return subprocess.check_output(["git",*args], cwd=ROOT, text=True).strip()

def test_01_block_recorded():
    data=_json(E/"port_owner_classification.json")
    assert data["status"]=="SWITCHOVER_BLOCKED_UNSAFE_8090_OWNER"
    assert data["safe_to_stop_8090"] is False
    assert data["switchover_performed"] is False

def test_02_doc_exists():
    assert (ROOT/"docs"/"FRONT_BRAIN_V9_RUNTIME_SWITCHOVER_8091_TO_8090_01.md").exists()

def test_03_immutability_passed():
    assert _json(E/"post_action_immutability_verify.json")["immutability_passed"] is True

def test_04_no_protected_staged():
    s=_git(["diff","--cached","--name-only"]).replace("\\","/")
    assert "memory/semantic" not in s and "trading/" not in s and "B8/" not in s and "tmp_agent/strategies" not in s
