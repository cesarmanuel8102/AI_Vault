import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_brain_v9_adapter_runtime_load_fix_01"
DOC = ROOT / "docs" / "FRONT_BRAIN_V9_ADAPTER_RUNTIME_LOAD_FIX_01.md"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_semantic_memory_lines_1715():
    semantic = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
    assert sum(1 for _ in semantic.open("rb")) == 1715


def test_02_faiss_ids_1616():
    ids = _json(ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json")
    assert len(ids) == 1616


def test_03_base_path_canonical():
    baseline = _json(EVIDENCE / "canonical_safety_baseline.json")
    assert baseline["base_path_canonical"] is True
    assert baseline["runtime_base_path"].endswith("AI_VAULT_CANONICAL")


def test_04_docs_file_exists():
    assert DOC.exists()


def test_05_runtime_probe_artifact_exists():
    assert (EVIDENCE / "runtime_openai_probe.json").exists()


def test_06_runtime_models_passed():
    probe = _json(EVIDENCE / "runtime_openai_probe.json")
    assert probe["runtime_models_passed"] is True


def test_07_runtime_chat_passed():
    probe = _json(EVIDENCE / "runtime_openai_probe.json")
    assert probe["runtime_chat_passed"] is True


def test_08_dialogue_summary_exists():
    assert (EVIDENCE / "codex_brain_direct_dialogue_summary.json").exists()


def test_09_dialogue_success_count_at_least_1():
    summary = _json(EVIDENCE / "codex_brain_direct_dialogue_summary.json")
    assert summary["successful_responses"] >= 1


def test_10_no_memory_semantic_staged():
    staged = _git(["diff", "--cached", "--name-only"])
    assert "memory/semantic" not in staged.replace("\\", "/")


def test_11_no_trading_staged():
    staged = _git(["diff", "--cached", "--name-only"])
    assert "trading/" not in staged.replace("\\", "/")


def test_12_no_b8_staged():
    staged = _git(["diff", "--cached", "--name-only"])
    assert "B8/" not in staged.replace("\\", "/")


def test_13_no_strategies_staged():
    staged = _git(["diff", "--cached", "--name-only"])
    assert "tmp_agent/strategies" not in staged.replace("\\", "/")


def test_14_no_env_staged():
    staged = _git(["diff", "--cached", "--name-only"])
    assert ".env" not in staged.splitlines()


def test_15_roadmap_status_json_valid():
    assert isinstance(_json(ROOT / "ROADMAP_STATUS.json"), dict)


def test_16_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
