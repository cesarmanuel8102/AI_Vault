import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_chat_ui_docker_networking_fix_01"


def _load_json(name: str):
    with (EVIDENCE / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def _git_staged_names():
    cp = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in cp.stdout.splitlines() if line.strip()]


def test_01_canonical_semantic_memory_lines_1715():
    assert _load_json("canonical_safety_baseline.json")["semantic_memory_lines"] == 1715


def test_02_canonical_faiss_ids_1616():
    assert _load_json("canonical_safety_baseline.json")["faiss_ids"] == 1616


def test_03_canonical_faiss_ntotal_1616_if_readable():
    baseline = _load_json("canonical_safety_baseline.json")
    if baseline.get("faiss_ntotal") is not None:
        assert baseline["faiss_ntotal"] == 1616


def test_04_base_path_is_canonical():
    baseline = _load_json("canonical_safety_baseline.json")
    assert baseline["runtime_base_path_canonical"] is True
    assert "AI_VAULT_CANONICAL" in baseline["runtime_base_path"]


def test_05_docker_open_webui_inventory_artifact_exists():
    assert (EVIDENCE / "docker_open_webui_inventory.json").exists()


def test_06_backend_connectivity_baseline_artifact_exists():
    assert (EVIDENCE / "backend_connectivity_baseline.json").exists()


def test_07_open_webui_start_plan_artifact_exists():
    assert (EVIDENCE / "open_webui_start_plan.json").exists()


def test_08_open_webui_apply_result_artifact_exists():
    assert (EVIDENCE / "open_webui_apply_result.json").exists()


def test_09_post_fix_ui_probe_artifact_exists():
    assert (EVIDENCE / "post_fix_ui_probe.json").exists()


def test_10_ollama_container_network_check_artifact_exists():
    assert (EVIDENCE / "ollama_container_network_check.json").exists()


def test_11_minimal_chat_ui_compatibility_check_artifact_exists():
    assert (EVIDENCE / "minimal_chat_ui_compatibility_check.json").exists()


def test_12_fix_classification_artifact_exists():
    assert (EVIDENCE / "fix_classification.json").exists()


def test_13_fix_classification_has_primary_result():
    assert _load_json("fix_classification.json").get("primary_result")


def test_14_no_memory_semantic_staged():
    assert not any(p.startswith("memory/semantic/") for p in _git_staged_names())


def test_15_no_trading_staged():
    assert not any(p == "trading" or p.startswith("trading/") for p in _git_staged_names())


def test_16_no_b8_staged():
    assert not any(p == "B8" or p.startswith("B8/") for p in _git_staged_names())


def test_17_no_tmp_agent_strategies_staged():
    assert not any(p.startswith("tmp_agent/strategies/") for p in _git_staged_names())


def test_18_no_env_staged():
    assert not any(p == ".env" or p.endswith("/.env") for p in _git_staged_names())


def test_19_roadmap_status_json_valid():
    with (ROOT / "ROADMAP_STATUS.json").open(encoding="utf-8") as fh:
        assert isinstance(json.load(fh), dict)


def test_20_migration_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
