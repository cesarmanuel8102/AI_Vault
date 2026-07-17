#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from v156_dynamic_test_support import *


def test_distinct_real_post_merge_topology_success():
    outcome, error, before, after, fake, topo = run_case()
    assert error is None and outcome["status"] == "POST_MERGE_RECOVERED_EXISTING_PR_V156"
    assert topo["historical"] != topo["pre"] != topo["feature"] != topo["merged"]
    state = json.loads(after["state"].decode())
    assert state["cycles"] == 2 and state["status"] == "WAITING_GITHUB"
    assert state["spec"]["expected_base_sha"] == topo["merged"]
    assert after["remote"] == state["last_head_sha"] != topo["old"]
    assert fake.issue_labels == {"loop:repairing"} and fake.pr_labels == {"loop:repairing"}
    assert topo["merged"] in fake.issue_body and topo["merged"] in fake.pr_body


def test_all_authorization_mismatches_fail_before_mutation():
    assert_pre_mutation_failure(fake_options={"live_base": "0" * 40})
    assert_pre_mutation_failure(auth_overrides={"approved_feature_head": "0" * 40})
    assert_pre_mutation_failure(auth_overrides={"approved_control_plane_commit": "0" * 40, "approved_merged_base": "0" * 40})
    assert_pre_mutation_failure(fake_options={"pr_head": "0" * 40})
    assert_pre_mutation_failure(fake_options={"issue_base": "0" * 40})
    assert_pre_mutation_failure(fake_options={"pr_base": "0" * 40})
    with tempfile.TemporaryDirectory() as td:
        wrong = Path(td) / "agent_worker.py"
        wrong.write_bytes(WORKER_PATH.read_bytes())
        assert_pre_mutation_failure(source_override=wrong)


def test_local_repo_cases_fail_before_mutation():
    for repo_case in ("missing", "nongit", "dirty", "ahead", "wrong_head"):
        assert_pre_mutation_failure(repo_case=repo_case)


def assert_full_rollback_case(setup=None, hooks=None):
    outcome, error, before, after, fake, topo = run_case(fake_setup=setup, hooks=hooks)
    assert outcome is None and error is not None
    assert before["state"] == after["state"] and before["worker"] == after["worker"]
    assert before["issue_body"] == after["issue_body"] and before["pr_body"] == after["pr_body"]
    assert before["issue_labels"] == after["issue_labels"] and before["pr_labels"] == after["pr_labels"]
    assert after["remote"] == topo["old"]


def test_remote_metadata_and_readback_failures_fully_roll_back():
    assert_full_rollback_case(lambda fake: setattr(fake, "body_fail_once", "issue"))
    assert_full_rollback_case(lambda fake: setattr(fake, "body_fail_once", "pr"))
    assert_full_rollback_case(lambda fake: setattr(fake, "label_fail_once", "issue"))
    assert_full_rollback_case(lambda fake: setattr(fake, "label_fail_once", "pr"))
    assert_full_rollback_case(lambda fake: setattr(fake, "readback_after_pr_label", "issue"))
    assert_full_rollback_case(lambda fake: setattr(fake, "readback_after_pr_label", "pr"))


def test_ordinary_failure_after_push_fully_rolls_back():
    def fail(**kwargs):
        raise RuntimeError("controlled after push")
    outcome, error, before, after, fake, topo = run_case(hooks={"after_push": fail})
    assert outcome is None and "controlled after push" in str(error)
    assert before["state"] == after["state"] and before["worker"] == after["worker"]
    assert before["issue_body"] == after["issue_body"] and before["pr_body"] == after["pr_body"]
    assert before["issue_labels"] == after["issue_labels"] and before["pr_labels"] == after["pr_labels"]
    assert after["remote"] == topo["old"]


def test_real_force_with_lease_conflict_returns_owner_action_required():
    third_party = {}
    def move_remote(repo_dir: Path, new_head: str, **kwargs):
        root = repo_dir.parent
        clone = root / "third-party"
        git(["clone", str(root / "remote.git"), str(clone)])
        git(["config", "user.name", "third"], clone)
        git(["config", "user.email", "third@example.invalid"], clone)
        git(["checkout", "-b", BRANCH, f"origin/{BRANCH}"], clone)
        (clone / "third-party.txt").write_text("third party\n", encoding="utf-8")
        git(["add", "third-party.txt"], clone)
        git(["commit", "-m", "third-party move"], clone)
        third_party["sha"] = git(["rev-parse", "HEAD"], clone)
        git(["push", "origin", f"HEAD:refs/heads/{BRANCH}"], clone)
        raise RuntimeError("trigger rollback after third-party movement")
    outcome, error, before, after, fake, topo = run_case(hooks={"after_push": move_remote})
    assert outcome is None and isinstance(error, helper.OwnerActionRequired)
    assert after["remote"] == third_party["sha"] and after["remote"] != topo["old"]
    rollback = error.evidence["rollback"]
    assert rollback["owner_action_required"] is True
    assert rollback["expected_lease_sha"]
    assert rollback["actual_remote_sha"] == third_party["sha"]
    assert rollback["attempted_rollback_target"] == topo["old"]


def test_partial_event_append_has_no_mixed_state():
    def partial(path: Path, record: str):
        with path.open("ab") as stream:
            stream.write(record.encode("utf-8")[:17])
        raise RuntimeError("partial event append")
    outcome, error, before, after, fake, topo = run_case(hooks={"partial_event_append": partial})
    assert outcome is None and "partial event append" in str(error)
    assert before["state"] == after["state"] and before["worker"] == after["worker"]
    assert after["remote"] == topo["old"]
    text = after["events"].decode("utf-8")
    assert "trusted_v156_dynamic_post_merge_recovery" not in text
    assert "trusted_v156_dynamic_post_merge_rollback" in text


def test_partial_state_and_remote_metadata_failures_roll_back():
    def partial_state(state_path: Path, state: dict):
        state_path.write_bytes(b'{"partial":')
        raise RuntimeError("partial state")
    outcome, error, before, after, fake, topo = run_case(hooks={"before_state_write": partial_state})
    assert outcome is None and before["state"] == after["state"] and after["remote"] == topo["old"]


if __name__ == "__main__":
    test_distinct_real_post_merge_topology_success()
    test_all_authorization_mismatches_fail_before_mutation()
    test_local_repo_cases_fail_before_mutation()
    test_remote_metadata_and_readback_failures_fully_roll_back()
    test_ordinary_failure_after_push_fully_rolls_back()
    test_real_force_with_lease_conflict_returns_owner_action_required()
    test_partial_event_append_has_no_mixed_state()
    test_partial_state_and_remote_metadata_failures_roll_back()
    print(json.dumps({
        "status": "PASS",
        "worker_version": "1.5.6",
        "topology": "historical->pre_pr10 + feature -> distinct_post_merge_base",
        "approved_control_plane_commit": "PASS",
        "pre_mutation_mismatches": "PASS",
        "remote_push_rollback": "PASS",
        "real_force_with_lease_conflict": "OWNER_ACTION_REQUIRED_PASS",
        "partial_event_append": "PASS",
    }, indent=2))
