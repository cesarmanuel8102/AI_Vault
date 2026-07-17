from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# 1. Transactional guards.
path = ROOT / "scripts/agent_loop/local_worker/v156_recovery_transaction.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '    if checkout_head != auth.approved_control_plane_commit:\n        raise ValueError("local control-plane checkout HEAD mismatch")\n    if auth.approved_control_plane_commit != auth.approved_merged_base:\n',
    '    if checkout_head != auth.approved_control_plane_commit:\n        raise ValueError("local control-plane checkout HEAD mismatch")\n    if git(["status", "--porcelain"], control_plane_root):\n        raise ValueError("local control-plane checkout is dirty")\n    if auth.approved_control_plane_commit != auth.approved_merged_base:\n',
    "clean checkout guard",
)
text = replace_once(
    text,
    '        if worker.sha256_file(installed_worker).upper() != auth.approved_worker_sha256:\n            raise ValueError("installed worker postcondition failed")\n\n        success_fields = {\n',
    '        if worker.sha256_file(installed_worker).upper() != auth.approved_worker_sha256:\n            raise ValueError("installed worker postcondition failed")\n        fire(hooks, "before_final_task_check")\n        if not worker.scheduled_task_disabled():\n            raise ValueError("scheduled task changed state during transaction")\n\n        success_fields = {\n',
    "task disabled postcondition",
)
text = replace_once(
    text,
    '            "task_disabled": worker.scheduled_task_disabled(),\n',
    '            "task_disabled": True,\n',
    "committed task evidence",
)
compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")

# 2. Contract flags.
path = ROOT / "scripts/agent_loop/local_worker/worker_contract.json"
contract = json.loads(path.read_text(encoding="utf-8"))
hardening = contract["hardening"]
hardening["v156_control_plane_clean_checkout"] = True
hardening["v156_task_disabled_transactional_postcondition"] = True
path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

# 3. Contract truthfulness assertions.
path = ROOT / "tests/contract/test_agent_loop_worker_hardening_02.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    'checks["v156_single_recovery_authority"] = True\nchecks["contract_truthfulness"] = True\n',
    'checks["v156_single_recovery_authority"] = True\nfor key in (\n    "v156_control_plane_clean_checkout",\n    "v156_task_disabled_transactional_postcondition",\n    "v156_operator_direct_audit",\n):\n    assert contract["hardening"][key] is True, key\nchecks["v156_final_transaction_guards"] = True\nchecks["contract_truthfulness"] = True\n',
    "hardening assertions",
)
compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")

# 4. Dynamic test support.
path = ROOT / "tests/contract/v156_dynamic_test_support.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    'def run_case(*, fake_options=None, auth_overrides=None, hooks=None, source_override=None, repo_case=None, fake_setup=None):\n',
    'def run_case(*, fake_options=None, auth_overrides=None, hooks=None, source_override=None, repo_case=None, fake_setup=None, control_dirty=False):\n',
    "run_case signature",
)
text = replace_once(
    text,
    '        topo = create_topology(root)\n        old_constants = (helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD)\n',
    '        topo = create_topology(root)\n        if control_dirty:\n            (topo["control"] / "uncommitted-control-change.txt").write_text("dirty\\n", encoding="utf-8")\n        old_constants = (helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD)\n',
    "dirty control fixture",
)
compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")

# 5. Behavioral tests.
path = ROOT / "tests/contract/test_agent_loop_worker_v156_post_merge_recovery.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '        wrong.write_bytes(WORKER_PATH.read_bytes())\n        assert_pre_mutation_failure(source_override=wrong)\n',
    '        wrong.write_bytes(WORKER_PATH.read_bytes())\n        assert_pre_mutation_failure(source_override=wrong)\n    assert_pre_mutation_failure(control_dirty=True)\n',
    "dirty control assertion",
)
anchor = 'def test_partial_event_append_has_no_mixed_state():\n'
if text.count(anchor) != 1:
    raise RuntimeError("task test anchor mismatch")
task_test = '''def test_task_state_change_before_commit_fully_rolls_back():
    def enable_task(**kwargs):
        helper.worker.scheduled_task_disabled = lambda: False
    outcome, error, before, after, fake, topo = run_case(hooks={"before_final_task_check": enable_task})
    assert outcome is None and "scheduled task changed state" in str(error)
    assert before["state"] == after["state"] and before["worker"] == after["worker"]
    assert before["issue_body"] == after["issue_body"] and before["pr_body"] == after["pr_body"]
    assert before["issue_labels"] == after["issue_labels"] and before["pr_labels"] == after["pr_labels"]
    assert after["remote"] == topo["old"]


'''
text = text.replace(anchor, task_test + anchor, 1)
text = replace_once(
    text,
    '    test_real_force_with_lease_conflict_returns_owner_action_required()\n    test_partial_event_append_has_no_mixed_state()\n',
    '    test_real_force_with_lease_conflict_returns_owner_action_required()\n    test_task_state_change_before_commit_fully_rolls_back()\n    test_partial_event_append_has_no_mixed_state()\n',
    "task test invocation",
)
text = replace_once(
    text,
    '        "partial_event_append": "PASS",\n',
    '        "partial_event_append": "PASS",\n        "control_plane_clean": "PASS",\n        "task_disabled_transactional_postcondition": "PASS",\n',
    "test evidence",
)
compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")

# 6. Control-plane record.
path = ROOT / "docs/agent_loop/control_plane/FRONT-AGENT-LOOP-V156-OPERATOR-FINAL-01.md"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    "# FRONT-AGENT-LOOP-V156-OPERATOR-FINAL-01\n\n"
    "## Status\n\nOPERATOR-OWNED FINALIZATION\n\n"
    "## Purpose\n\nFinalize the v1.5.6 post-merge recovery transaction after concurrent control-plane activity.\n\n"
    "## Scope\n\n"
    "- preserve Issue #5 and PR #6;\n"
    "- retain one dynamic post-merge recovery authority;\n"
    "- require an exact, clean approved control-plane checkout;\n"
    "- require the scheduled worker task to remain Disabled through transaction commit;\n"
    "- preserve force-with-lease conflict handling as OWNER_ACTION_REQUIRED;\n"
    "- run Windows and Ubuntu contracts before merge;\n"
    "- no deployment, Kimi execution, `--once`, third pilot, trading work, or canonical synchronization.\n",
    encoding="utf-8",
)

# Remove the one-shot application machinery from the resulting commit.
(ROOT / ".github/workflows/operator-apply-v156-final-clean.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
print("OPERATOR_V156_FINAL_PATCH_APPLIED")
