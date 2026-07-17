#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "scripts/agent_loop/local_worker/v156_post_merge_recovery.py"
WORKER_PATH = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
_spec = importlib.util.spec_from_file_location("v156_dynamic", HELPER_PATH)
helper = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(helper)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
BRANCH = "agent/pilot-20260716-091529"
BASE_BRANCH = "codex/own-capital-sustainable-return"
REPO = "cesarmanuel8102/AI_Vault"
OWNER = "cesarmanuel8102"
PILOT_FILES = sorted(helper.PILOT_FILES)


def git(args: list[str], cwd: Path | None = None, *, check: bool = True) -> str:
    cp = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and cp.returncode != 0:
        raise RuntimeError(cp.stdout)
    return cp.stdout.strip()


def bare_ref(remote: Path, ref: str) -> str:
    return git(["--git-dir", str(remote), "rev-parse", ref])


def create_topology(root: Path) -> dict:
    remote = root / "remote.git"
    git(["init", "--bare", str(remote)])
    builder = root / "builder"
    git(["clone", str(remote), str(builder)])
    git(["config", "user.name", "test"], builder)
    git(["config", "user.email", "test@example.invalid"], builder)
    (builder / "historical.txt").write_text("historical\n", encoding="utf-8")
    git(["add", "historical.txt"], builder)
    git(["commit", "-m", "historical"], builder)
    historical = git(["rev-parse", "HEAD"], builder)
    git(["checkout", "-b", BASE_BRANCH], builder)
    (builder / "pre.txt").write_text("pre-pr10\n", encoding="utf-8")
    git(["add", "pre.txt"], builder)
    git(["commit", "-m", "pre pr10 base"], builder)
    pre = git(["rev-parse", "HEAD"], builder)
    git(["checkout", "-b", "feature", pre], builder)
    source = builder / "scripts/agent_loop/local_worker/agent_worker.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(WORKER_PATH.read_bytes())
    (builder / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(["add", "scripts/agent_loop/local_worker/agent_worker.py", "feature.txt"], builder)
    git(["commit", "-m", "feature head"], builder)
    feature = git(["rev-parse", "HEAD"], builder)
    git(["checkout", BASE_BRANCH], builder)
    git(["reset", "--hard", pre], builder)
    git(["merge", "--no-ff", "--no-edit", feature], builder)
    merged = git(["rev-parse", "HEAD"], builder)
    assert merged != feature and feature != pre and pre != historical
    git(["push", "origin", f"HEAD:refs/heads/{BASE_BRANCH}"], builder)
    git(["checkout", "-b", BRANCH, historical], builder)
    for rel in PILOT_FILES:
        path = builder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel + "\n", encoding="utf-8")
    git(["add", *PILOT_FILES], builder)
    git(["commit", "-m", "preserved pilot"], builder)
    old = git(["rev-parse", "HEAD"], builder)
    git(["push", "origin", f"HEAD:refs/heads/{BRANCH}"], builder)
    pilot = root / "pilot"
    git(["clone", str(remote), str(pilot)])
    git(["checkout", "-b", BRANCH, f"origin/{BRANCH}"], pilot)
    git(["config", "user.name", "test"], pilot)
    git(["config", "user.email", "test@example.invalid"], pilot)
    control = root / "control"
    git(["clone", str(remote), str(control)])
    git(["checkout", "--detach", merged], control)
    return {"remote": remote, "builder": builder, "pilot": pilot, "control": control, "historical": historical, "pre": pre, "feature": feature, "merged": merged, "old": old, "source": control / "scripts/agent_loop/local_worker/agent_worker.py"}


def issue_body(base: str) -> str:
    spec = {"schema_version": 1, "front_id": FRONT, "repo": REPO, "owner": OWNER, "base_branch": BASE_BRANCH, "expected_base_sha": base, "work_branch": BRANCH, "objective": "pilot", "test_profile": "pilot", "max_kimi_cycles": 3, "allowed_paths": PILOT_FILES, "forbidden_paths": sorted(helper.worker.REQUIRED_FORBIDDEN_PATHS)}
    return "<!-- AGENT_LOOP_SPEC " + json.dumps(spec, separators=(",", ":")) + " AGENT_LOOP_SPEC -->"


def write_install(root: Path, topo: dict) -> tuple[dict, Path]:
    (root / "state").mkdir(exist_ok=True)
    (root / "worker").mkdir(exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    (root / "worker/agent_worker.py").write_text("old-worker\n", encoding="utf-8")
    state = {"issue_number": 5, "front": FRONT, "spec": {"front_id": FRONT, "work_branch": BRANCH, "expected_base_sha": topo["historical"], "base_branch": BASE_BRANCH}, "repo_dir": str(topo["pilot"]), "pr_number": 6, "cycles": 3, "status": "WAITING_GITHUB", "last_head_sha": topo["old"], "trusted_v154_resume_done": True, "terminal_notified": True}
    state_path = root / "state/issue-5.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    events = [
        {"kind": "trusted_v154_resume_existing_pr", "issue": 5, "pr": 6, "base": topo["historical"], "head": topo["old"]},
        {"kind": "repair_local_gate_failed", "issue": 5, "pr": 6, "cycle": 3, "cycle_before": 2, "cycle_after": 3, "failure_class": "MODEL_CONTENT_FAILURE", "current_head": topo["old"], "expected_base": topo["historical"]},
    ]
    (root / "reports/worker-events.jsonl").write_text("\n".join(json.dumps(x) for x in events) + "\n", encoding="utf-8")
    return {"install_root": str(root), "repo": REPO, "owner": OWNER, "base_branch": BASE_BRANCH}, state_path


def ancestor_status(repo: Path, ancestor: str, descendant: str) -> str:
    if ancestor == descendant:
        return "identical"
    cp = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return "ahead" if cp.returncode == 0 else "diverged"


class FakeGitHub:
    def __init__(self, topo: dict, *, issue_base: str | None = None, pr_base: str | None = None, pr_head: str | None = None, live_base: str | None = None):
        self.topo = topo
        self.issue_body = issue_body(issue_base or topo["historical"])
        self.pr_body = f"EXPECTED_BASE_SHA: {pr_base or topo['historical']}"
        self.issue_labels = {"loop:repairing"}
        self.pr_labels = {"loop:token-exhausted"}
        self.pr_head_override = pr_head
        self.live_base_override = live_base
        self.body_fail_once: str | None = None
        self.label_fail_once: str | None = None
        self.readback_fail_once: str | None = None
        self.readback_after_pr_label: str | None = None
        self.mutation_count = 0

    def remote_pr_head(self) -> str:
        return self.pr_head_override or bare_ref(self.topo["remote"], f"refs/heads/{BRANCH}")

    def gh_json(self, args: list[str]):
        if args[:2] == ["issue", "view"]:
            labels = self.issue_labels
            if self.readback_fail_once == "issue":
                self.readback_fail_once = None
                labels = {"loop:blocked"}
            return {"number": 5, "state": "OPEN", "author": {"login": OWNER}, "body": self.issue_body, "labels": [{"name": x} for x in sorted(labels)], "url": "issue"}
        if args[:2] == ["pr", "view"]:
            labels = self.pr_labels
            if self.readback_fail_once == "pr":
                self.readback_fail_once = None
                labels = {"loop:blocked"}
            return {"number": 6, "state": "OPEN", "isDraft": True, "headRefName": BRANCH, "headRefOid": self.remote_pr_head(), "baseRefName": BASE_BRANCH, "body": self.pr_body, "labels": [{"name": x} for x in sorted(labels)], "url": "pr"}
        if args[:1] == ["api"] and "/compare/" in args[1]:
            ancestor, descendant = args[1].split("/compare/", 1)[1].split("...", 1)
            return {"status": ancestor_status(self.topo["control"], ancestor, descendant)}
        if args[:1] == ["api"] and "/git/ref/heads/" in args[1]:
            value = self.live_base_override or bare_ref(self.topo["remote"], f"refs/heads/{BASE_BRANCH}")
            return {"object": {"sha": value}}
        raise AssertionError(args)

    def update_issue_body(self, repo: str, number: int, body: str):
        self.mutation_count += 1
        if self.body_fail_once == "issue":
            self.body_fail_once = None
            raise RuntimeError("issue body fail")
        self.issue_body = body

    def update_pr_body(self, repo: str, number: int, body: str):
        self.mutation_count += 1
        if self.body_fail_once == "pr":
            self.body_fail_once = None
            raise RuntimeError("pr body fail")
        self.pr_body = body

    def edit_labels(self, repo: str, number: int, add=(), remove=()):
        self.mutation_count += 1
        key = "issue" if int(number) == 5 else "pr"
        if self.label_fail_once == key:
            self.label_fail_once = None
            raise RuntimeError(key + " label fail")
        labels = self.issue_labels if key == "issue" else self.pr_labels
        labels.difference_update(remove)
        labels.update(add)
        if key == "pr" and self.readback_after_pr_label:
            self.readback_fail_once = self.readback_after_pr_label
            self.readback_after_pr_label = None


def patch_worker(fake: FakeGitHub):
    names = ["gh_json", "update_issue_body", "update_pr_body", "edit_labels", "read_issue_labels", "read_pr_labels", "restore_label_set", "pr_changed_files", "scheduled_task_disabled", "issue_comments"]
    originals = {name: getattr(helper.worker, name) for name in names}
    helper.worker.gh_json = fake.gh_json
    helper.worker.update_issue_body = fake.update_issue_body
    helper.worker.update_pr_body = fake.update_pr_body
    helper.worker.edit_labels = fake.edit_labels
    helper.worker.read_issue_labels = lambda repo, number: fake.gh_json(["issue", "view"])
    helper.worker.read_pr_labels = lambda repo, number: fake.gh_json(["pr", "view"])
    helper.worker.restore_label_set = lambda repo, number, labels: setattr(fake, "issue_labels" if int(number) == 5 else "pr_labels", set(labels))
    helper.worker.pr_changed_files = lambda repo, number: PILOT_FILES
    helper.worker.scheduled_task_disabled = lambda: True
    helper.worker.issue_comments = lambda repo, number: [{"body": "[AGENT-LOOP][TOKEN_EXHAUSTED]\n\nMaximum Kimi cycles reached. Human audit required."} for _ in range(3)]
    return originals


def restore_worker(originals: dict):
    for name, value in originals.items():
        setattr(helper.worker, name, value)


def auth(topo: dict, **overrides) -> helper.Authorization:
    values = dict(historical_base=topo["historical"], pre_pr10_base=topo["pre"], approved_feature_head=topo["feature"], approved_merged_base=topo["merged"], approved_control_plane_commit=topo["merged"], expected_old_pr_head=topo["old"], expected_front=FRONT, expected_pr_number=6, expected_work_branch=BRANCH, approved_worker_sha256=helper.worker.sha256_file(topo["source"]).upper())
    values.update(overrides)
    return helper.Authorization(**values)


def run_case(*, fake_options=None, auth_overrides=None, hooks=None, source_override=None, repo_case=None, fake_setup=None):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        topo = create_topology(root)
        old_constants = (helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD)
        helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD = topo["historical"], topo["pre"], topo["old"]
        cfg, state_path = write_install(root, topo)
        if repo_case == "missing":
            state = json.loads(state_path.read_text(encoding="utf-8")); state["repo_dir"] = str(root / "missing-repo"); state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        elif repo_case == "nongit":
            nongit = root / "nongit"; nongit.mkdir(); state = json.loads(state_path.read_text(encoding="utf-8")); state["repo_dir"] = str(nongit); state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        elif repo_case == "dirty":
            (topo["pilot"] / "dirty.txt").write_text("dirty", encoding="utf-8")
        elif repo_case == "ahead":
            (topo["pilot"] / "ahead.txt").write_text("ahead", encoding="utf-8"); git(["add", "ahead.txt"], topo["pilot"]); git(["commit", "-m", "unexpected ahead"], topo["pilot"])
        elif repo_case == "wrong_head":
            git(["checkout", "--detach", topo["historical"]], topo["pilot"])
        fake = FakeGitHub(topo, **(fake_options or {}))
        if fake_setup is not None:
            fake_setup(fake)
        originals = patch_worker(fake)
        before = {"state": state_path.read_bytes(), "worker": (root / "worker/agent_worker.py").read_bytes(), "issue_body": fake.issue_body, "pr_body": fake.pr_body, "issue_labels": set(fake.issue_labels), "pr_labels": set(fake.pr_labels), "events": (root / "reports/worker-events.jsonl").read_bytes()}
        try:
            outcome = helper.run_locked(cfg, auth(topo, **(auth_overrides or {})), source_worker=source_override or topo["source"], control_plane_root=topo["control"], hooks=hooks)
            error = None
        except Exception as exc:
            outcome = None
            error = exc
        after = {"state": state_path.read_bytes(), "worker": (root / "worker/agent_worker.py").read_bytes(), "issue_body": fake.issue_body, "pr_body": fake.pr_body, "issue_labels": set(fake.issue_labels), "pr_labels": set(fake.pr_labels), "events": (root / "reports/worker-events.jsonl").read_bytes(), "remote": bare_ref(topo["remote"], f"refs/heads/{BRANCH}")}
        snapshot = (outcome, error, before, after, fake, topo)
        restore_worker(originals)
        helper.common.HISTORICAL_BASE, helper.common.PRE_PR10_BASE, helper.common.OLD_PR_HEAD = old_constants
        return snapshot


def assert_pre_mutation_failure(**kwargs):
    outcome, error, before, after, fake, topo = run_case(**kwargs)
    assert outcome is None and error is not None
    assert before["state"] == after["state"] and before["worker"] == after["worker"]
    assert before["issue_body"] == after["issue_body"] and before["pr_body"] == after["pr_body"]
    assert before["issue_labels"] == after["issue_labels"] and before["pr_labels"] == after["pr_labels"]
    assert after["remote"] == topo["old"] and fake.mutation_count == 0
