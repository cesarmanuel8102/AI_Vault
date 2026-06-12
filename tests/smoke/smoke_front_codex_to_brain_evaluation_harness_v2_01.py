import json
import subprocess
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = ROOT / "tests" / "tools" / "codex_brain_eval_harness.py"
spec = importlib.util.spec_from_file_location("codex_brain_eval_harness", HARNESS_PATH)
harness = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(harness)
load_suite = harness.load_suite
score_results = harness.score_results


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_harness_imports_and_suite_loads():
    prompts = load_suite(ROOT / "tests/fixtures/default_codex_brain_eval_suite.json")
    assert len(prompts) == 24


def test_02_mini_suite_loads_8():
    prompts = load_suite(ROOT / "tests/fixtures/default_codex_brain_eval_suite.json", mini=True)
    assert len(prompts) == 8


def test_03_scoring_detects_timeout_and_metadata():
    scored = score_results([{
        "content": "El modelo tardó demasiado",
        "brain": {"intent": "QUERY", "route": "x", "governance_applied": True, "no_cot_leak": True, "canonical_path": "C:/AI_VAULT_CANONICAL"},
        "error": None,
    }])
    assert scored["timeout_fallback_count"] == 1
    assert scored["metadata_full_rate"] == 1.0


def test_04_no_protected_paths_staged():
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
