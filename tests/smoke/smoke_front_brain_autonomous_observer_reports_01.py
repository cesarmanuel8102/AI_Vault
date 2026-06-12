import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "tests" / "fixtures" / "autonomous_observer_report_example.json"
DOC = ROOT / "docs" / "BRAIN_AUTONOMOUS_OBSERVER_REPORT_SCHEMA.md"

REQUIRED_FIELDS = {
    "front",
    "objective",
    "actions_taken",
    "files_changed",
    "tests_run",
    "evidence_paths",
    "gates_passed",
    "gates_failed",
    "memory_mutated",
    "faiss_mutated",
    "trading_touched",
    "secrets_exposed",
    "raw_cot_exposed",
    "runtime_used",
    "next_recommended_front",
    "human_review_needed",
}


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_example_report_has_required_fields():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert REQUIRED_FIELDS <= set(data)
    assert isinstance(data["actions_taken"], list)
    assert isinstance(data["tests_run"], list)
    assert isinstance(data["evidence_paths"], list)


def test_02_safety_flags_are_boolean_and_safe_in_example():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for key in ["memory_mutated", "faiss_mutated", "trading_touched", "secrets_exposed", "raw_cot_exposed", "human_review_needed"]:
        assert isinstance(data[key], bool)
    assert data["memory_mutated"] is False
    assert data["faiss_mutated"] is False
    assert data["trading_touched"] is False
    assert data["secrets_exposed"] is False
    assert data["raw_cot_exposed"] is False


def test_03_schema_doc_mentions_required_fields():
    text = DOC.read_text(encoding="utf-8")
    for field in sorted(REQUIRED_FIELDS):
        assert field in text


def test_04_no_protected_paths_staged():
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
