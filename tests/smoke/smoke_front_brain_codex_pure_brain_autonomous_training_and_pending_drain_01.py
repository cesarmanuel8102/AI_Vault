import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "tmp_agent" / "front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01"

def load(name):
    return json.loads((FRONT / name).read_text(encoding="utf-8"))

def test_required_artifacts_and_metrics():
    for name in ["state_lock.json", "brain_runtime_and_memory_baseline.json", "pending_memory_inventory.json", "training_dataset.json", "baseline_brain_eval.json", "unified_candidate_review_and_drain.json", "canonical_promotion_execution.json", "post_training_eval.json", "safety_regression_check.json"]:
        assert (FRONT / name).exists(), name
    assert (FRONT / "codex_brain_training_loop.jsonl").exists()
    loop_lines = [line for line in (FRONT / "codex_brain_training_loop.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(loop_lines) >= 18
    review = load("unified_candidate_review_and_drain.json")
    promo = load("canonical_promotion_execution.json")
    safety = load("safety_regression_check.json")
    assert review["unresolved_pending_after_review"] == 0
    if review["approved_count"] > 0:
        assert promo["promoted_count"] == review["approved_count"]
    assert promo["semantic_lines_delta"] == promo["promoted_count"]
    assert promo["faiss_ids_delta"] == promo["promoted_count"]
    assert promo["faiss_ntotal_delta"] == promo["promoted_count"]
    assert not safety["safety_regression"]

def test_no_prohibited_paths_or_raw_cot():
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in FRONT.glob("*.json") if p.name != "openapi_8091.json")
    assert "raw chain-of-thought" not in text.lower()
    changed = set(subprocess.run(["git", "diff", "--name-only"], cwd=ROOT, text=True, capture_output=True).stdout.splitlines())
    assert not any(p.startswith(("trading/", "B8/", "tmp_agent/strategies/")) for p in changed)

def test_roadmap_and_ledger_valid():
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
