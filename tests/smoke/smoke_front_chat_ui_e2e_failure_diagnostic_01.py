import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_chat_ui_e2e_failure_diagnostic_01"


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
    assert "AI_VAULT_CANONICAL" in baseline["runtime_base_path_stdout"]


def test_05_service_port_inventory_artifact_exists():
    assert (EVIDENCE / "service_port_inventory.json").exists()


def test_06_endpoint_probe_results_artifact_exists():
    assert (EVIDENCE / "endpoint_probe_results.json").exists()


def test_07_openapi_route_discovery_artifact_exists():
    assert (EVIDENCE / "openapi_route_discovery.json").exists()


def test_08_direct_backend_chat_probe_artifact_exists():
    assert (EVIDENCE / "direct_backend_chat_probe.json").exists()


def test_09_open_webui_provider_diagnostic_artifact_exists():
    assert (EVIDENCE / "open_webui_provider_diagnostic.json").exists()


def test_10_streaming_sse_compatibility_artifact_exists():
    assert (EVIDENCE / "streaming_sse_compatibility.json").exists()


def test_11_session_retrieval_diagnostic_artifact_exists():
    assert (EVIDENCE / "session_retrieval_diagnostic.json").exists()


def test_12_failure_classification_artifact_exists():
    assert (EVIDENCE / "failure_classification.json").exists()


def test_13_fix_plan_package_artifact_exists():
    assert (EVIDENCE / "fix_plan_package.json").exists()


def test_14_failure_classification_has_primary_failure():
    assert _load_json("failure_classification.json").get("primary_failure")


def test_15_fix_plan_has_recommended_fix_front():
    assert _load_json("fix_plan_package.json").get("recommended_fix_front")


def test_16_no_memory_semantic_staged():
    assert not any(p.startswith("memory/semantic/") for p in _git_staged_names())


def test_17_no_trading_staged():
    assert not any(p == "trading" or p.startswith("trading/") for p in _git_staged_names())


def test_18_no_b8_staged():
    assert not any(p == "B8" or p.startswith("B8/") for p in _git_staged_names())


def test_19_no_tmp_agent_strategies_staged():
    assert not any(p.startswith("tmp_agent/strategies/") for p in _git_staged_names())


def test_20_no_env_staged():
    assert not any(p == ".env" or p.endswith("/.env") for p in _git_staged_names())


def test_21_roadmap_status_json_valid():
    with (ROOT / "ROADMAP_STATUS.json").open(encoding="utf-8") as fh:
        assert isinstance(json.load(fh), dict)


def test_22_migration_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
