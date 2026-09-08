"""Contract for the pre-authorized, JIT-bound BRAIN-101 R5-R19 backlog."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "roadmap" / "BRAIN_101_MANIFEST.json"
ROADMAP = ROOT / "docs" / "roadmap" / "BRAIN_101_ROADMAP.md"
PHASES = tuple(f"R{phase}" for phase in range(5, 20))
PHASE_ORDER = {phase: index for index, phase in enumerate(PHASES, start=5)}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _planned_items(manifest: dict) -> dict:
    return {
        item_id: item
        for item_id, item in manifest["roadmap_items"].items()
        if item.get("status") == "PLANNED_UNBOUND"
    }


def _assert_acyclic(items: dict, roots: set[str]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str) -> None:
        assert item_id not in visiting
        if item_id in visited:
            return
        visiting.add(item_id)
        for dependency in items[item_id]["dependencies"]:
            assert dependency in items or dependency in roots
            if dependency in items:
                visit(dependency)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in items:
        visit(item_id)


def test_r5_through_r19_are_a_complete_non_executable_pre_authorized_backlog():
    manifest = _manifest()
    planned = _planned_items(manifest)
    assert set(item["phase"] for item in planned.values()) == set(PHASES)
    assert all(item_id.startswith(f"{item['phase']}.") for item_id, item in planned.items())
    assert all(item["status"] == "PLANNED_UNBOUND" for item in planned.values())
    assert all(item["automation"]["jit_binding_required"] is True for item in planned.values())
    assert all(item["automation"]["dispatchable"] is False for item in planned.values())
    assert all("expected_base_sha" not in item for item in planned.values())
    assert all("front_id" not in item["automation"] for item in planned.values())


def test_planned_backlog_has_unique_ids_acyclic_defined_and_phase_ordered_dependencies():
    manifest = _manifest()
    planned = _planned_items(manifest)
    assert len(planned) == len(set(planned))
    _assert_acyclic(planned, {"R5.3"})
    for item in planned.values():
        for dependency in item["dependencies"]:
            assert dependency in planned or dependency == "R5.3"
            dependency_phase = planned.get(dependency, {"phase": "R5"})["phase"]
            dependency_order = PHASE_ORDER[dependency_phase]
            assert dependency_order <= PHASE_ORDER[item["phase"]]


def test_r5_2_closeout_activates_exactly_one_jit_bound_r5_3_successor():
    manifest = _manifest()
    items = manifest["roadmap_items"]
    active = [item_id for item_id, item in items.items() if item["status"] == "AUTHORIZED_ACTIVE"]
    assert active == ["R5.3"]
    assert items["R4.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert items["R4.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert items["R4.3"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert items["R5.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert items["R5.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    binding = items["R5.3"]["automation"]
    assert binding["dispatchable"] is True
    assert binding["jit_binding_completed"] is True
    assert binding["executor"] == "codex_control_plane"
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["front_id"] == "BRAIN-101-R5-3-AGENT-V2-PLANNING-EVALUATION-PERSISTENCE-01"
    assert binding["work_branch"] == "control-plane/r5-3-agent-v2-planning-evaluation-persistence"


def test_closeout_preserves_pre_r5_history_except_the_declared_r4_3_transition():
    manifest = _manifest()
    baseline = json.loads(
        subprocess.check_output(
            ["git", "show", "HEAD:docs/roadmap/BRAIN_101_MANIFEST.json"],
            cwd=ROOT,
            text=True,
        )
    )
    current_pre_r5 = {
        item_id: item
        for item_id, item in manifest["roadmap_items"].items()
        if not item_id.startswith(tuple(f"R{phase}." for phase in range(5, 20)))
        and item_id != "R4.3"
    }
    baseline_pre_r5 = {
        item_id: item
        for item_id, item in baseline["roadmap_items"].items()
        if not item_id.startswith(tuple(f"R{phase}." for phase in range(5, 20)))
        and item_id != "R4.3"
    }
    assert current_pre_r5 == baseline_pre_r5


def test_manifest_roadmap_sha256_matches_the_exact_canonical_roadmap_bytes():
    manifest = _manifest()
    assert manifest["roadmap_sha256"] == hashlib.sha256(ROADMAP.read_bytes()).hexdigest()


def test_r5_3_is_the_only_jit_bound_active_item_after_r5_2_closeout():
    planned = _planned_items(_manifest())
    assert "R5.1" not in planned
    assert "R5.2" not in planned
    assert "R5.3" not in planned
    assert {item_id for item_id, item in planned.items() if item["phase"] == "R5"} == {"R5.4"}
    assert planned["R5.4"]["dependencies"] == ["R5.3"]


def test_jit_binding_contract_requires_live_identity_scope_and_verification_before_activation():
    manifest = _manifest()
    requirements = manifest["roadmap_execution_binding_v1"]
    assert requirements["planned_status"] == "PLANNED_UNBOUND"
    assert requirements["activation_status"] == "AUTHORIZED_ACTIVE"
    assert requirements["required_live_fields"] == [
        "expected_base_sha",
        "front_id",
        "work_branch",
        "allowed_paths",
        "forbidden_paths",
        "test_commands",
        "acceptance",
        "rollback",
        "evidence_path",
    ]
    assert requirements["activation_requires_exactly_one"] is True


def test_financial_and_certification_backlog_preserve_constitutional_limits():
    planned = _planned_items(_manifest())
    for item in planned.values():
        limits = item["hard_limits"]
        assert limits["human_final_authority"] is True
        assert limits["auto_merge"] is False
        assert limits["canonical_local_sync"] is False
        assert limits["live_trading"] is False
        assert limits["real_money"] is False
        assert limits["persistent_agent_loop"] == "DEFERRED"
    assert all(item["deployment_intent"] == "PAPER_ONLY" for item in planned.values() if item["phase"] in {"R11", "R12", "R13", "R14", "R15", "R16"})
    assert "JUSTIFIABLY_DEFERRED" in planned["R17.2"]["acceptance_intent"]
    assert "mandatory_certification_gates" in planned["R19.1"]["acceptance_intent"]
    assert "persistent_agent_loop_deferred" in planned["R19.1"]["negative_acceptance"]
