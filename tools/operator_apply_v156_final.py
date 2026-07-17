from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSACTION = ROOT / "scripts/agent_loop/local_worker/v156_recovery_transaction.py"
SUPPORT = ROOT / "tests/contract/v156_dynamic_test_support.py"
TEST = ROOT / "tests/contract/test_agent_loop_worker_v156_post_merge_recovery.py"
CONTRACT = ROOT / "scripts/agent_loop/local_worker/worker_contract.json"
HARDENING = ROOT / "tests/contract/test_agent_loop_worker_hardening_02.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


transaction = TRANSACTION.read_text(encoding="utf-8")
transaction = replace_once(
    transaction,
    '''    if checkout_head != auth.approved_control_plane_commit:\n        raise ValueError("local control-plane checkout HEAD mismatch")\n    if auth.approved_control_plane_commit != auth.approved_merged_base:\n''',
    '''    if checkout_head != auth.approved_control_plane_commit:\n        raise ValueError("local control-plane checkout HEAD mismatch")\n    if git(["status", "--porcelain"], control_plane_root):\n        raise ValueError("local control-plane checkout is dirty")\n    if auth.approved_control_plane_commit != auth.approved_merged_base:\n''',
    "control-plane clean check",
)
transaction = replace_once(
    transaction,
    '''        if worker.sha256_file(installed_worker).upper() != auth.approved_worker_sha256:\n            raise ValueError("installed worker postcondition failed")\n\n        success_fields = {\n''',
    '''        if worker.sha256_file(installed_worker).upper() != auth.approved_worker_sha256:\n            raise ValueError("installed worker postcondition failed")\n        fire(hooks, "before_final_task_check")\n        if not worker.scheduled_task_disabled():\n            raise ValueError("scheduled task changed state during transaction")\n\n        success_fields = {\n''',
    "final task-state check",
)
transaction = replace_once(
    transaction,
    '            "task_disabled": worker.scheduled_task_disabled(),\n',
    '            "task_disabled": True,\n',
    "committed task evidence",
)
compile(transaction, str(TRANSACTION), "exec")
TRANSACTION.write_text(transaction, encoding="utf-8")

support = SUPPORT.read_text(encoding="utf-8")
support = replace_once(
    support,
    '''def run_case(*, fake_options=None, auth_overrides=None, hooks=None, source_override=None, repo_case=None, fake_setup=None):\n''',
    '''def run_case(*, fake_options=None, auth_overrides=None, hooks=None, source_override=None, repo_case=None, fake_setup=None, control_dirty=False):\n''',
    "run_case signature",
)
support = replace_once(
    support,
    '''        topo = create_topology(root)\n        old_constants = (helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD)\n''',
    '''        topo = create_topology(root)\n        if control_dirty:\n            (topo["control"] / "uncommitted-control-change.txt").write_text("dirty\\n", encoding="utf-8")\n        old_constants = (helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD)\n''',
    "control dirty fixture",
)
compile(support, str(SUPPORT), "exec")
SUPPORT.write_text(support, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
test = replace_once(
    test,
    '''    assert_pre_mutation_failure(source_override=wrong)\n''',
    '''    assert_pre_mutation_failure(source_override=wrong)\n    assert_pre_mutation_failure(control_dirty=True)\n''',
    "dirty control-plane assertion",
)
anchor = '''def test_partial_event_append_has_no_mixed_state():\n'''
if test.count(anchor) != 1:
    raise RuntimeError("task-state test anchor mismatch")
task_test = '''def test_task_state_change_before_commit_fully_rolls_back():\n    def enable_task(**kwargs):\n        helper.worker.scheduled_task_disabled = lambda: False\n    outcome, error, before, after, fake, topo = run_case(hooks={"before_final_task_check": enable_task})\n    assert outcome is None and "scheduled task changed state" in str(error)\n    assert before["state"] == after["state"] and before["worker"] == after["worker"]\n    assert before["issue_body"] == after["issue_body"] and before["pr_body"] == after["pr_body"]\n    assert before["issue_labels"] == after["issue_labels"] and before["pr_labels"] == after["pr_labels"]\n    assert after["remote"] == topo["old"]\n\n\n'''
test = test.replace(anchor, task_test + anchor, 1)
test = replace_once(
    test,
    '''    test_real_force_with_lease_conflict_returns_owner_action_required()\n    test_partial_event_append_has_no_mixed_state()\n''',
    '''    test_real_force_with_lease_conflict_returns_owner_action_required()\n    test_task_state_change_before_commit_fully_rolls_back()\n    test_partial_event_append_has_no_mixed_state()\n''',
    "task-state test invocation",
)
test = replace_once(
    test,
    '''        "partial_event_append": "PASS",\n''',
    '''        "partial_event_append": "PASS",\n        "control_plane_clean": "PASS",\n        "task_disabled_transactional_postcondition": "PASS",\n''',
    "test report evidence",
)
compile(test, str(TEST), "exec")
TEST.write_text(test, encoding="utf-8")

contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
contract["hardening"]["v156_control_plane_clean_checkout"] = True
contract["hardening"]["v156_task_disabled_transactional_postcondition"] = True
contract["hardening"]["v156_operator_direct_audit"] = True
CONTRACT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

hardening = HARDENING.read_text(encoding="utf-8")
anchor2 = 'checks["contract_truthfulness"] = True\n'
if hardening.count(anchor2) != 1:
    raise RuntimeError("hardening anchor mismatch")
assertions = '''for key in (\n    "v156_control_plane_clean_checkout",\n    "v156_task_disabled_transactional_postcondition",\n    "v156_operator_direct_audit",\n):\n    assert contract["hardening"][key] is True, key\nchecks["v156_final_transaction_guards"] = True\n'''
hardening = hardening.replace(anchor2, assertions + anchor2, 1)
compile(hardening, str(HARDENING), "exec")
HARDENING.write_text(hardening, encoding="utf-8")

print(json.dumps({"status": "PATCHED", "control_plane_clean": True, "task_disabled_transactional": True}, indent=2))
