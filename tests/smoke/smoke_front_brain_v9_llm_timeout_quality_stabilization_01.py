import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_brain_v9_llm_timeout_quality_stabilization_01"
SESSION = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
DOC = ROOT / "docs" / "FRONT_BRAIN_V9_LLM_TIMEOUT_QUALITY_STABILIZATION_01.md"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_doc_exists():
    assert DOC.exists()


def test_02_session_uses_configurable_timeout_and_max_time():
    text = SESSION.read_text(encoding="utf-8")
    assert "BRAIN_CHAT_LLM_TIMEOUT" in text
    assert "max_time=llm_timeout_s" in text
    assert "timeout=llm_timeout_s + 5.0" in text


def test_03_governed_eval_fallback_exists():
    text = SESSION.read_text(encoding="utf-8")
    assert "governed_eval_fallback" in text
    assert "_governed_self_improvement_eval_fallback" in text


def test_04_mini_suite_passed():
    data = _json(EVIDENCE / "mini_quality_suite_results_passed.json")
    assert data["passed"] is True
    assert data["successful_responses"] >= 8
    assert data["timeout_fallback_count"] <= 2
    assert data["metadata_full_rate"] == 1.0
    assert data["raw_cot_count"] == 0


def test_05_immutability_passed():
    assert _json(EVIDENCE / "post_action_immutability_verify.json")["immutability_passed"] is True


def test_06_no_protected_paths_staged():
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
    assert ".env" not in staged.splitlines()
