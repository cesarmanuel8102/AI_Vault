"""tests/smoke/smoke_front_chat_retrieval_injection_authorization_01.py
FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-AUTHORIZATION-01 — Smoke tests
"""

import json
import subprocess
from pathlib import Path

from brain.chat_retrieval_injection_authorization import (
    front_id,
    protected_files_requiring_authorization,
    current_chat_flow,
    proposed_insertion_point,
    retrieval_injection_contract,
    proposed_patch_plan,
    future_tests_required,
    authorization_decision_template,
    summarize_authorization,
)


def test_01_module_imports():
    import brain.chat_retrieval_injection_authorization as mod
    assert callable(mod.front_id)
    assert callable(mod.summarize_authorization)


def test_02_front_id_exact():
    assert front_id() == "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-AUTHORIZATION-01"


def test_03_protected_files_include_session_py():
    files = protected_files_requiring_authorization()
    paths = [f["path"] for f in files]
    assert "tmp_agent/brain_v9/core/session.py" in paths


def test_04_current_chat_flow_includes_main_and_session():
    flow = current_chat_flow()
    files = [step["file"] for step in flow]
    assert "tmp_agent/brain_v9/main.py" in files
    assert "tmp_agent/brain_v9/core/session.py" in files


def test_05_proposed_insertion_point_has_protected_file():
    ins = proposed_insertion_point()
    assert ins["protected_file"] is True
    assert ins["file"] == "tmp_agent/brain_v9/core/session.py"


def test_06_contract_read_only_memory_true():
    contract = retrieval_injection_contract()
    assert contract["read_only_memory"] is True


def test_07_contract_read_only_faiss_true():
    contract = retrieval_injection_contract()
    assert contract["read_only_faiss"] is True


def test_08_contract_max_retrieval_hits_le_3():
    contract = retrieval_injection_contract()
    assert contract["max_retrieval_hits"] <= 3


def test_09_contract_max_context_chars_le_2500():
    contract = retrieval_injection_contract()
    assert contract["max_context_chars"] <= 2500


def test_10_contract_no_raw_cot_true():
    contract = retrieval_injection_contract()
    assert contract["no_raw_cot"] is True


def test_11_contract_no_connectors_true():
    contract = retrieval_injection_contract()
    assert contract["no_connectors"] is True


def test_12_contract_no_external_network_true():
    contract = retrieval_injection_contract()
    assert contract["no_external_network"] is True


def test_13_patch_plan_implementation_later_true():
    plan = proposed_patch_plan()
    assert plan["implementation_must_happen_in_later_front"] is True
    assert "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01" in plan["later_front_name"]


def test_14_patch_plan_no_memory_mutation():
    plan = proposed_patch_plan()
    steps = " ".join(plan["steps"])
    assert "No modification to memory" in steps or "memory/semantic" in steps


def test_15_authorization_requires_user_decision():
    auth = authorization_decision_template()
    assert auth["required_user_decision"] is True


def test_16_next_front_if_authorized_correct():
    auth = authorization_decision_template()
    assert auth["next_front_if_authorized"] == "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01"


def test_17_no_semantic_memory_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_18_no_faiss_index_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/semantic_memory_faiss.index"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_19_no_protected_files_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env", "session.py", "main.py", "execution_gate.py", "brain/curated_runtime_lookup.py", "trading", "B8", "tmp_agent/strategies"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_20_roadmap_valid():
    roadmap = Path("ROADMAP_STATUS.json")
    assert roadmap.exists()
    obj = json.loads(roadmap.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)


def test_21_ledger_exists():
    assert Path("docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_22_summary_status_is_authorization_required():
    summary = summarize_authorization()
    assert summary["status"] == "AUTHORIZATION_REQUIRED"
    assert summary["protected_runtime_change_required"] is True


def test_23_memory_not_mutated():
    summary = summarize_authorization()
    assert summary["memory_mutated"] is False


def test_24_faiss_not_mutated():
    summary = summarize_authorization()
    assert summary["faiss_mutated"] is False
