from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    "tmp_agent/brain_v9/memory/promotion_candidate_promoter.py",
    "tmp_agent/brain_v9/memory/promotion_pipeline_adapter.py",
    "tmp_agent/brain_v9/learning/capability_evaluator.py",
]


def test_active_modules_do_not_hardcode_legacy_repo_paths():
    forbidden = (
        "C:/AI_VAULT",
        "C:\\AI_VAULT",
        "AI_VAULT_CANONICAL",
    )
    for rel in TARGETS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{rel} still contains {marker}"


def test_active_modules_use_owned_or_central_path_boundaries():
    promoter = (ROOT / TARGETS[0]).read_text(encoding="utf-8")
    adapter = (ROOT / TARGETS[1]).read_text(encoding="utf-8")
    evaluator = (ROOT / TARGETS[2]).read_text(encoding="utf-8")

    # R6.2 delegates promotion ownership to MemoryService and accepts an explicit
    # isolated root; it must not derive a canonical root from global config.
    assert "from tmp_agent.brain_v9.core.memory_service import MemoryService" in promoter
    assert "BASE_PATH" not in promoter
    assert "from tmp_agent.brain_v9.config import BASE_PATH" in adapter
    assert "ROOT = BASE_PATH" in adapter
    assert "from brain_v9.config import BASE_PATH" in evaluator
    assert "cwd=str(BASE_PATH)" in evaluator
