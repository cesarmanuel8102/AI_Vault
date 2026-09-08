"""R5.1 contract for the source-evidenced Agent V2 runtime baseline."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/roadmap/evidence/BRAIN_101_R5_1_AGENT_V2_RUNTIME_BASELINE.json"
CLOSEOUT_EVIDENCE = (
    ROOT
    / "docs/roadmap/evidence/BRAIN_101_R5_1_AGENT_V2_RUNTIME_BASELINE_CLOSEOUT.json"
)
MANIFEST = ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json"

R5_1_SOURCE_COMMIT = "8f923a318b39b0d24e14def6e079bb6a31ae0650"
R5_1_MERGE_COMMIT = "0e4ba1286f5ff8f6ee90908efc472c5790595409"

EXPECTED_PATHS = {
    "agent_v2_api": "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py",
    "agent_v2_runtime_selector": "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py",
    "agent_v2_langgraph_runtime": "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
    "agent_v2_native_fallback": "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py",
    "legacy_chat_route": "tmp_agent/brain_v9/routes/chat_entrypoint_routes.py",
    "legacy_chat_service": "tmp_agent/brain_v9/core/chat_entrypoint_service.py",
    "legacy_session_router": "tmp_agent/brain_v9/core/session.py",
    "legacy_session_llm_router": "tmp_agent/brain_v9/core/session_routing_helpers.py",
    "legacy_session_agent_router": "tmp_agent/brain_v9/core/session_agent_route.py",
    "intent_adapter": "tmp_agent/brain_v9/core/agent_kernel_v2/intent_adapter.py",
    "agent_v2_planner": "tmp_agent/brain_v9/core/agent_kernel_v2/planner.py",
}

EXPECTED_PATH_IDS = {
    "direct_llm",
    "brain_evidence",
    "mixed_reasoning",
    "learning_external",
    "code_task",
    "financial_research",
}


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _closeout_evidence() -> dict:
    return json.loads(CLOSEOUT_EVIDENCE.read_text(encoding="utf-8"))


def test_r5_1_evidence_is_bound_to_the_governed_front_and_hard_limits():
    evidence = _evidence()

    assert evidence["schema_version"] == 1
    assert evidence["evidence_type"] == "BRAIN_101_R5_1_AGENT_V2_RUNTIME_BASELINE"
    assert evidence["controller"] == "CODEX_GOVERNED_CONTROLLER"
    assert evidence["roadmap_id"] == "BRAIN-101"
    assert evidence["roadmap_item_id"] == "R5.1"
    assert evidence["front_id"] == "BRAIN-101-R5-1-AGENT-V2-RUNTIME-BASELINE-01"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["baseline_only"] is True
    assert evidence["runtime_behavior_modified"] is False
    assert evidence["scheduler_activated"] is False
    assert evidence["hard_limits"] == {
        "human_final_authority": True,
        "auto_merge": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "persistent_agent_loop": "DEFERRED",
    }


def test_r5_1_inventory_references_live_source_bytes_at_the_evidence_base():
    evidence = _evidence()
    base_sha = evidence["canonical_base_sha"]
    assert len(base_sha) == 40
    assert _git("rev-parse", f"{base_sha}^{{commit}}") == base_sha

    inventory = {entry["id"]: entry for entry in evidence["runtime_inventory"]}
    assert set(inventory) == set(EXPECTED_PATHS)
    for entry_id, expected_path in EXPECTED_PATHS.items():
        entry = inventory[entry_id]
        assert entry["path"] == expected_path
        source_bytes = _git_bytes("show", f"{base_sha}:{expected_path}")
        source = source_bytes.decode("utf-8")
        assert entry["source_anchor"] in source
        assert entry["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()


def test_r5_1_records_each_required_cognitive_path_with_source_backed_boundaries():
    evidence = _evidence()
    base_sha = evidence["canonical_base_sha"]
    paths = {entry["id"]: entry for entry in evidence["cognitive_path_boundaries"]}
    assert set(paths) == EXPECTED_PATH_IDS

    for path_id, entry in paths.items():
        assert entry["owner"]
        assert entry["boundary"]
        assert entry["execution_claim"] in {"read_only", "governed", "not_routed_by_agent_v2"}
        path = entry["source"]["path"]
        anchor = entry["source"]["anchor"]
        assert path in EXPECTED_PATHS.values()
        assert anchor in _git("show", f"{base_sha}:{path}")

    assert paths["direct_llm"]["execution_claim"] == "read_only"
    assert paths["financial_research"]["execution_claim"] == "not_routed_by_agent_v2"


def test_r5_1_makes_parallel_paths_and_non_convergence_explicit():
    evidence = _evidence()
    findings = {entry["id"]: entry for entry in evidence["parallel_path_findings"]}
    assert set(findings) == {"legacy_chat_entrypoint", "legacy_session_router", "native_runtime_fallback"}
    for finding in findings.values():
        assert finding["containment_status"] == "INVENTORIED_NOT_MIGRATED"
        source = finding["source"]
        assert source["path"] in EXPECTED_PATHS.values()
        assert source["anchor"] in _git(
            "show", f"{evidence['canonical_base_sha']}:{source['path']}"
        )


def test_r5_1_front_diff_is_limited_to_its_evidence_and_contract():
    evidence = _evidence()
    changed = set(
        filter(
            None,
            _git("diff", "--name-only", f"{evidence['canonical_base_sha']}..HEAD").splitlines(),
        )
    )
    assert changed <= {
        "docs/roadmap/evidence/BRAIN_101_R5_1_AGENT_V2_RUNTIME_BASELINE.json",
        "tests/contract/test_r5_1_agent_v2_runtime_baseline.py",
    }


def test_r5_1_closeout_is_bound_to_the_verified_merge_and_baseline_evidence():
    closeout = _closeout_evidence()

    assert closeout["schema_version"] == 1
    assert closeout["evidence_type"] == "BRAIN_101_R5_1_AGENT_V2_RUNTIME_BASELINE_CLOSEOUT"
    assert closeout["controller"] == "CODEX_GOVERNED_CONTROLLER"
    assert closeout["roadmap_id"] == "BRAIN-101"
    assert closeout["roadmap_item_id"] == "R5.1"
    assert closeout["parent_front_id"] == "BRAIN-101-R5-1-AGENT-V2-RUNTIME-BASELINE-01"
    assert closeout["parent_source_commit"] == R5_1_SOURCE_COMMIT
    assert closeout["parent_merge_commit"] == R5_1_MERGE_COMMIT
    assert closeout["source_evidence_path"] == str(EVIDENCE.relative_to(ROOT)).replace("\\", "/")
    assert closeout["result"] == "CLOSED_RUNTIME_VERIFIED"
    assert closeout["hard_limits"] == _evidence()["hard_limits"]


def test_r5_1_closeout_activates_only_jit_bound_r5_2():
    items = _manifest()["roadmap_items"]
    active = [item_id for item_id, item in items.items() if item["status"] == "AUTHORIZED_ACTIVE"]

    assert items["R5.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert active == ["R5.2"]
    binding = items["R5.2"]["automation"]
    assert binding["jit_binding_completed"] is True
    assert binding["dispatchable"] is True
    assert binding["front_id"] == "BRAIN-101-R5-2-AGENT-V2-LIFECYCLE-CHECKPOINTS-01"
    assert binding["work_branch"] == "control-plane/r5-2-agent-v2-lifecycle-checkpoints"
    assert binding["expected_base_sha_source"] == (
        "sequenceRoadmap resolves the exact live canonical integration-branch head at governed dispatch"
    )
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["evidence_path"] == (
        "docs/roadmap/evidence/BRAIN_101_R5_2_AGENT_V2_LIFECYCLE_CHECKPOINTS.json"
    )
    assert binding["allowed_paths"]
    assert binding["forbidden_paths"]
    assert binding["test_commands"]
    assert binding["acceptance"]
    assert binding["rollback"]
