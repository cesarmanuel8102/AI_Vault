import json
from pathlib import Path

import pytest


@pytest.mark.unit
def test_pattern_extractor_detects_multi_agent_debate(tmp_path):
    from brain_v9.learning.pattern_extractor import extract_patterns

    root_index = tmp_path / "root_index.json"
    root_index.write_text(json.dumps([{"name": "tests"}, {"name": "requirements.txt"}]), encoding="utf-8")
    dep_hints = tmp_path / "dependency_hints.json"
    dep_hints.write_text(json.dumps({"requirements.txt": "tool calling\nsubprocess"}), encoding="utf-8")
    snippets = tmp_path / "priority_file_snippets.json"
    snippets.write_text(json.dumps([
        {"path": "python/packages/autogen-agentchat/src/groupchat.py", "score": 9, "size": 1200, "excerpt": "critic judge multi-agent debate tool handoff"},
    ]), encoding="utf-8")
    manifest = {
        "source_id": "github_microsoft_autogen_20260507",
        "root_index_path": str(root_index),
        "dependency_hints_path": str(dep_hints),
        "priority_file_snippets_path": str(snippets),
    }
    curation = {"recommended_action": "analyze"}
    repo_metadata = tmp_path / "repo_metadata.json"
    repo_metadata.write_text(json.dumps({"full_name": "microsoft/autogen", "name": "autogen"}), encoding="utf-8")
    readme = tmp_path / "README.snapshot.md"
    readme.write_text("Multi-agent group chat with critic and judge roles.", encoding="utf-8")
    out = tmp_path / "pattern_report.json"

    report = extract_patterns(manifest, curation, repo_metadata, readme, out)

    pattern_ids = {p["pattern_id"] for p in report["patterns"]}
    assert "structured_multi_agent_debate" in pattern_ids
    assert "ci_backed_regression_harness" in pattern_ids
    assert "structured_tool_dispatch" in pattern_ids
    debate = next(p for p in report["patterns"] if p["pattern_id"] == "structured_multi_agent_debate")
    assert debate["evidence_refs"]
    assert debate["evidence_refs"][0]["source_file"].endswith("groupchat.py")


@pytest.mark.unit
def test_build_learning_status_creates_scorecard_and_attribution(monkeypatch, tmp_path):
    import brain_v9.learning.status as status_mod

    monkeypatch.setattr(status_mod, "EXTERNAL_INTEL_ROOT", tmp_path / "external_intel")
    monkeypatch.setattr(status_mod, "KNOWLEDGE_EXTERNAL_ROOT", tmp_path / "knowledge" / "external")
    monkeypatch.setattr(status_mod, "CAPABILITY_STATE_ROOT", tmp_path / "state" / "capabilities")
    monkeypatch.setattr(status_mod, "CAPABILITY_SCORECARD_PATH", tmp_path / "state" / "capabilities" / "capability_scorecard_latest.json")
    monkeypatch.setattr(status_mod, "LEARNING_STATUS_PATH", tmp_path / "state" / "learning_status_latest.json")
    monkeypatch.setattr(status_mod, "LEARNING_REFRESH_STATE_PATH", tmp_path / "state" / "learning_refresh_state.json")
    monkeypatch.setattr(status_mod, "LEARNING_EVENTS_PATH", tmp_path / "logs" / "learning_events.ndjson")
    monkeypatch.setattr(status_mod, "PROPOSAL_REGISTRY_PATH", tmp_path / "state" / "capabilities" / "proposal_registry_latest.json")
    monkeypatch.setattr(status_mod, "_append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(status_mod, "load_source_registry", lambda: {"sources": [{"owner": "microsoft", "repo": "autogen", "enabled": True, "category": "agent_orchestration", "priority": 10, "rationale": "test"}]})
    monkeypatch.setattr(status_mod, "active_sources", lambda max_sources=None: [{"owner": "microsoft", "repo": "autogen", "enabled": True, "category": "agent_orchestration", "priority": 10, "rationale": "test"}])
    monkeypatch.setattr(status_mod, "load_registry", lambda: {"proposals": []})
    monkeypatch.setattr(status_mod, "build_patch_proposals", lambda hypothesis_rows: {
        "updated_utc": "2026-05-08T00:00:00Z",
        "status": "proposal_only",
        "created_proposal_ids": ["PROP_TEST_001"],
        "proposals": [{
            "proposal_id": "PROP_TEST_001",
            "hypothesis_id": hypothesis_rows[0]["hypothesis_id"],
            "semantic_key": hypothesis_rows[0]["semantic_key"],
            "target_capability": hypothesis_rows[0]["target_capability"],
            "current_state": "pending_review",
            "allowed_next_states": ["approved_for_sandbox", "rejected"],
            "state_history": [{"state": "pending_review", "ts_utc": "2026-05-08T00:00:00Z", "actor": "system", "reason": "created"}],
            "linked_sources": hypothesis_rows[0]["linked_sources"],
            "source_attribution": [hypothesis_rows[0]["source_attribution"]],
            "evidence_strength_score": 0.72,
            "risk_score": 0.4,
            "files_to_modify": ["session.py"],
        }],
    })

    def fake_ingest(owner, repo, force_refresh=False):
        local_dir = tmp_path / "external_intel" / "github" / "microsoft_autogen"
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "repo_metadata.json").write_text(json.dumps({"full_name": "microsoft/autogen", "topics": ["multi-agent"]}), encoding="utf-8")
        (local_dir / "README.snapshot.md").write_text("critic judge multi-agent", encoding="utf-8")
        (local_dir / "root_index.json").write_text(json.dumps([{"name": "tests"}, {"name": "requirements.txt"}]), encoding="utf-8")
        (local_dir / "dependency_hints.json").write_text(json.dumps({"requirements.txt": "tool calling"}), encoding="utf-8")
        return {
            "source_id": "github_microsoft_autogen_20260507",
            "source_type": "github_repo",
            "url": "https://github.com/microsoft/autogen",
            "status": "downloaded",
            "local_path": str(local_dir),
            "root_index_path": str(local_dir / "root_index.json"),
            "dependency_hints_path": str(local_dir / "dependency_hints.json"),
        }

    def fake_curate(source_manifest, repo_metadata_path, output_path):
        payload = {
            "source_id": source_manifest["source_id"],
            "curation_score": 8.5,
            "risk_score": 3.0,
            "license_status": "compatible",
            "recommended_action": "analyze",
            "repo": {"tests_present": True, "docs_present": True, "dependency_files": ["requirements.txt"]},
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(status_mod, "ingest_github_repo", fake_ingest)
    monkeypatch.setattr(status_mod, "curate_repo", fake_curate)

    payload = status_mod.build_learning_status(refresh=False)

    assert payload["status"] == "ok"
    assert payload["panels"]["sources"][0]["source_id"] == "github_microsoft_autogen_20260507"
    assert payload["panels"]["ingestion"]["catalog_size"] == 1
    assert status_mod.CAPABILITY_SCORECARD_PATH.exists()
    scorecard = json.loads(status_mod.CAPABILITY_SCORECARD_PATH.read_text(encoding="utf-8"))
    assert "planning_coherence" in scorecard["capabilities"]
    assert payload["panels"]["proposals"]
    assert payload["panels"]["semantic_dedup"]
    assert payload["activation"]["externally_informed_learning_active"] is False
    assert "capability_curves" in payload["panels"]["learning_curve"]
    attribution_map = tmp_path / "knowledge" / "external" / "github" / "microsoft_autogen" / "attribution_map.json"
    assert attribution_map.exists()


@pytest.mark.unit
def test_repo_curator_surfaces_tests_and_dependency_risk(tmp_path):
    from brain_v9.learning.repo_curator import curate_repo

    metadata_path = tmp_path / "repo_metadata.json"
    metadata_path.write_text(json.dumps({
        "full_name": "example/agents",
        "stargazers_count": 1200,
        "open_issues_count": 12,
        "size": 1200,
        "archived": False,
        "disabled": False,
        "has_wiki": True,
        "has_issues": True,
        "default_branch": "main",
        "updated_at": "2026-05-01T00:00:00Z",
        "license": {"spdx_id": "MIT"},
        "language": "Python",
        "topics": ["agents", "orchestration"],
    }), encoding="utf-8")
    root_index = tmp_path / "root_index.json"
    root_index.write_text(json.dumps([
        {"name": "tests"},
        {"name": "requirements.txt"},
        {"name": ".env"},
    ]), encoding="utf-8")
    dep_hints = tmp_path / "dependency_hints.json"
    dep_hints.write_text(json.dumps({"requirements.txt": "subprocess\n"}), encoding="utf-8")
    manifest = {
        "source_id": "github_example_agents_20260508",
        "root_index_path": str(root_index),
        "dependency_hints_path": str(dep_hints),
    }
    output_path = tmp_path / "curation_report.json"

    report = curate_repo(manifest, metadata_path, output_path)

    assert report["repo"]["tests_present"] is True
    assert "requirements.txt" in report["repo"]["dependency_files"]
    assert report["dependency_risk_flags"]
    assert "apparent_secrets_in_root" in report["reject_reasons"]


@pytest.mark.unit
def test_hypothesis_ids_are_source_scoped(tmp_path):
    from brain_v9.learning.capability_hypothesis_generator import generate_hypotheses

    pattern_report = {
        "patterns": [
            {"pattern_id": "structured_multi_agent_debate", "risk": 4},
            {"pattern_id": "structured_tool_dispatch", "risk": 2},
        ]
    }
    left = generate_hypotheses({"source_id": "github_alpha_repo_20260508"}, pattern_report, tmp_path / "left.json")
    right = generate_hypotheses({"source_id": "github_beta_repo_20260508"}, pattern_report, tmp_path / "right.json")

    left_ids = {h["hypothesis_id"] for h in left["hypotheses"]}
    right_ids = {h["hypothesis_id"] for h in right["hypotheses"]}

    assert left_ids.isdisjoint(right_ids)


@pytest.mark.unit
def test_patch_advisor_deduplicates_by_semantic_key(monkeypatch, tmp_path):
    import brain_v9.learning.patch_advisor as patch_mod

    monkeypatch.setattr(patch_mod, "PROPOSAL_REGISTRY_PATH", tmp_path / "proposal_registry_latest.json")

    registry = patch_mod.build_patch_proposals([
        {
            "hypothesis_id": "HYP_A_001",
            "semantic_key": "tool_use_accuracy:tool_routing",
            "target_capability": "tool_use_accuracy",
            "linked_sources": ["github_a"],
            "source_attribution": {"source_id": "github_a", "pattern_id": "structured_tool_dispatch", "semantic_family": "tool_routing", "evidence_refs": [{"source_file": "README.snapshot.md"}]},
        },
        {
            "hypothesis_id": "HYP_B_001",
            "semantic_key": "tool_use_accuracy:tool_routing",
            "target_capability": "tool_use_accuracy",
            "linked_sources": ["github_b"],
            "source_attribution": {"source_id": "github_b", "pattern_id": "structured_tool_dispatch", "semantic_family": "tool_routing", "evidence_refs": [{"source_file": "pyproject.toml"}]},
        },
    ])

    proposals = registry["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["current_state"] == "pending_review"
    assert proposals[0]["state_history"][0]["state"] == "pending_review"
    assert sorted(proposals[0]["linked_sources"]) == ["github_a", "github_b"]


@pytest.mark.unit
def test_patch_advisor_preserves_existing_state_by_semantic_key(monkeypatch, tmp_path):
    import brain_v9.learning.patch_advisor as patch_mod

    monkeypatch.setattr(patch_mod, "PROPOSAL_REGISTRY_PATH", tmp_path / "proposal_registry_latest.json")
    patch_mod.PROPOSAL_REGISTRY_PATH.write_text(json.dumps({
        "updated_utc": "2026-05-08T00:00:00Z",
        "status": "proposal_only",
        "proposals": [
            {
                "proposal_id": "PROP_EXISTING",
                "semantic_key": "tool_use_accuracy:tool_routing",
                "current_state": "evaluation_pending",
                "state_history": [{"state": "evaluation_pending", "ts_utc": "2026-05-08T00:00:00Z", "actor": "tester", "reason": "preserved"}],
                "sandbox_runs": [{"run_id": "RUN_1", "status": "evaluation_pending"}],
                "last_sandbox_run_id": "RUN_1",
                "evaluation_history": [{"run_id": "RUN_1", "verdict": "needs_more_tests"}],
                "last_evaluator_verdict": "needs_more_tests",
            }
        ],
    }), encoding="utf-8")

    registry = patch_mod.build_patch_proposals([
        {
            "hypothesis_id": "HYP_A_001",
            "semantic_key": "tool_use_accuracy:tool_routing",
            "target_capability": "tool_use_accuracy",
            "linked_sources": ["github_a"],
            "source_attribution": {"source_id": "github_a", "pattern_id": "structured_tool_dispatch", "semantic_family": "tool_routing", "evidence_refs": [{"source_file": "README.snapshot.md"}]},
        },
    ])

    proposal = registry["proposals"][0]
    assert proposal["proposal_id"] == "PROP_EXISTING"
    assert proposal["current_state"] == "evaluation_pending"
    assert proposal["state_history"][-1]["reason"] == "preserved"
    assert proposal["last_sandbox_run_id"] == "RUN_1"
    assert proposal["evaluation_history"][0]["verdict"] == "needs_more_tests"


@pytest.mark.unit
def test_proposal_governance_ranks_and_transitions(monkeypatch, tmp_path):
    import brain_v9.learning.proposal_governance as gov_mod

    registry_path = tmp_path / "proposal_registry_latest.json"
    events = []
    monkeypatch.setattr(gov_mod, "PROPOSAL_REGISTRY_PATH", registry_path)
    monkeypatch.setattr(gov_mod, "_append_event", lambda event, payload: events.append((event, payload)))

    registry = {
        "updated_utc": "2026-05-08T00:00:00Z",
        "status": "proposal_only",
        "proposals": [
            {
                "proposal_id": "PROP_A",
                "hypothesis_id": "HYP_A",
                "semantic_key": "planning_coherence:multi_agent_debate",
                "files_to_modify": ["a.py", "b.py"],
                "risk_level": "medium",
                "current_state": "pending_review",
                "linked_sources": ["github_a", "github_b"],
                "source_attribution": [
                    {"source_id": "github_a", "evidence_refs": [{"source_file": "README.snapshot.md"}]},
                    {"source_id": "github_b", "evidence_refs": [{"source_file": "groupchat.py"}]},
                ],
                "state_history": [{"state": "pending_review", "ts_utc": "2026-05-08T00:00:00Z", "actor": "system", "reason": "created"}],
                "target_capability": "planning_coherence",
            },
            {
                "proposal_id": "PROP_B",
                "hypothesis_id": "HYP_B",
                "semantic_key": "governance_quality:dependency_governance",
                "files_to_modify": ["c.py", "d.py", "e.py"],
                "risk_level": "medium",
                "current_state": "pending_review",
                "linked_sources": ["github_c"],
                "source_attribution": [
                    {"source_id": "github_c", "evidence_refs": [{"source_file": "pyproject.toml"}]},
                ],
                "state_history": [{"state": "pending_review", "ts_utc": "2026-05-08T00:00:00Z", "actor": "system", "reason": "created"}],
                "target_capability": "governance_quality",
            },
        ],
    }
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    loaded = gov_mod.load_registry()
    assert loaded["proposals"][0]["proposal_id"] == "PROP_A"
    assert loaded["proposals"][0]["proposal_priority_score"] >= loaded["proposals"][1]["proposal_priority_score"]
    assert loaded["proposals"][0]["allowed_next_states"] == ["approved_for_sandbox", "rejected"]

    invalid = gov_mod.transition_proposal_state("PROP_A", "candidate_promote", actor="tester", reason="skip")
    assert invalid["success"] is False
    assert invalid["error"] == "invalid_transition"

    valid = gov_mod.transition_proposal_state("PROP_A", "approved_for_sandbox", actor="tester", reason="review_ok")
    assert valid["success"] is True
    assert valid["to_state"] == "approved_for_sandbox"
    assert valid["proposal"]["current_state"] == "approved_for_sandbox"
    assert valid["proposal"]["state_history"][-1]["actor"] == "tester"
    assert events[-1][0] == "proposal_state_changed"


@pytest.mark.unit
def test_sandbox_executor_runs_py_compile_and_advances_state(monkeypatch, tmp_path):
    import brain_v9.learning.proposal_governance as gov_mod
    import brain_v9.learning.sandbox_executor as sandbox_mod

    registry_path = tmp_path / "proposal_registry_latest.json"
    sandbox_root = tmp_path / "sandboxes"
    events = []
    monkeypatch.setattr(gov_mod, "PROPOSAL_REGISTRY_PATH", registry_path)
    monkeypatch.setattr(sandbox_mod, "SANDBOX_ROOT", sandbox_root)
    monkeypatch.setattr(sandbox_mod, "BASE_PATH", tmp_path)
    monkeypatch.setattr(sandbox_mod, "_append_event", lambda event, payload: events.append((event, payload)))

    source_file = tmp_path / "tmp_agent" / "brain_v9" / "source.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("x = 1\n", encoding="utf-8")

    registry = {
        "updated_utc": "2026-05-08T00:00:00Z",
        "status": "proposal_only",
        "proposals": [
            {
                "proposal_id": "PROP_SANDBOX",
                "hypothesis_id": "HYP_SANDBOX",
                "semantic_key": "execution_reliability:retry_logic",
                "files_to_modify": [str(source_file)],
                "risk_level": "medium",
                "current_state": "approved_for_sandbox",
                "linked_sources": ["github_a"],
                "source_attribution": [{"source_id": "github_a", "evidence_refs": [{"source_file": "README.snapshot.md"}]}],
                "state_history": [{"state": "pending_review", "ts_utc": "2026-05-08T00:00:00Z", "actor": "system", "reason": "created"}],
                "target_capability": "execution_reliability",
                "allowed_next_states": ["sandbox_running", "rejected"],
            }
        ],
    }
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    result = sandbox_mod.execute_sandbox_run("PROP_SANDBOX", actor="tester", reason="sandbox_smoke")

    assert result["success"] is True
    assert result["result_state"] == "evaluation_pending"
    assert result["proposal"]["current_state"] == "evaluation_pending"
    assert result["proposal"]["sandbox_runs"]
    run = result["proposal"]["sandbox_runs"][-1]
    assert Path(run["manifest_path"]).exists()
    assert Path(run["evaluation_summary_path"]).exists()
    assert Path(run["rollback_manifest_path"]).exists()
    assert result["validation"]["py_compile"]["ok"] is True
    event_names = [name for name, _payload in events]
    assert "sandbox_run_started" in event_names
    assert "sandbox_run_completed" in event_names
    assert "proposal_state_changed" in event_names


@pytest.mark.unit
def test_read_learning_status_merges_live_registry(monkeypatch, tmp_path):
    import brain_v9.learning.status as status_mod

    status_path = tmp_path / "learning_status_latest.json"
    registry_path = tmp_path / "proposal_registry_latest.json"
    monkeypatch.setattr(status_mod, "LEARNING_STATUS_PATH", status_path)

    status_path.write_text(json.dumps({
        "milestone": "learning_phase_1_3",
        "panels": {"proposals": [], "sandbox": {"total_runs": 0}},
        "rules": {"sandbox_execution_active": False},
    }), encoding="utf-8")
    registry_path.write_text(json.dumps({
        "updated_utc": "2026-05-08T00:00:00Z",
        "proposals": [
            {
                "proposal_id": "PROP_X",
                "current_state": "evaluation_pending",
                "allowed_next_states": ["candidate_promote", "rejected", "rolled_back"],
                "sandbox_runs": [{"run_id": "RUN_X", "status": "evaluation_pending", "completed_at_utc": "2026-05-08T00:00:01Z", "evaluator_verdict": "needs_more_tests", "evaluation_completed_at_utc": "2026-05-08T00:00:02Z", "evaluation_report_path": "C:\\tmp\\eval.json"}],
            }
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(status_mod, "load_registry", lambda: json.loads(registry_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(status_mod, "load_source_registry", lambda: {"sources": [{"owner": "microsoft", "repo": "autogen", "enabled": True}]})
    monkeypatch.setattr(status_mod, "_read_learning_events", lambda limit=25: [])

    payload = status_mod.read_learning_status()

    assert payload["milestone"] == "learning_phase_1_5"
    assert payload["panels"]["proposals"][0]["proposal_id"] == "PROP_X"
    assert payload["panels"]["sandbox"]["total_runs"] == 1
    assert payload["panels"]["evaluation"]["total_evaluations"] == 1
    assert payload["rules"]["sandbox_execution_active"] is True


@pytest.mark.unit
def test_capability_evaluator_promotes_candidate_with_evidence(monkeypatch, tmp_path):
    import brain_v9.learning.capability_evaluator as eval_mod
    import brain_v9.learning.proposal_governance as gov_mod

    registry_path = tmp_path / "proposal_registry_latest.json"
    scorecard_path = tmp_path / "capability_scorecard_latest.json"
    run_dir = tmp_path / "runs" / "RUN_1"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "sandbox_manifest.json"
    rollback_path = run_dir / "rollback_manifest.json"
    summary_path = run_dir / "evaluation_summary.json"
    events = []

    monkeypatch.setattr(gov_mod, "PROPOSAL_REGISTRY_PATH", registry_path)
    monkeypatch.setattr(eval_mod, "CAPABILITY_SCORECARD_PATH", scorecard_path)
    monkeypatch.setattr(eval_mod, "_append_event", lambda event, payload: events.append((event, payload)))
    monkeypatch.setattr(eval_mod, "_targeted_regression", lambda _cap: {"ok": True, "tests": ["dummy"], "returncode": 0, "stdout_tail": "", "stderr_tail": ""})

    manifest_path.write_text(json.dumps({"copied_files": [{"status": "copied"}]}), encoding="utf-8")
    rollback_path.write_text(json.dumps({"files": [{"source_path": "a.py"}]}), encoding="utf-8")
    summary_path.write_text(json.dumps({
        "validation": {"py_compile": {"ok": True}},
        "production_integrity": {
            "before": [{"source_path": "a.py", "exists": True, "sha256": "1", "size_bytes": 1}],
            "after": [{"source_path": "a.py", "exists": True, "sha256": "1", "size_bytes": 1}],
        },
        "before_capability_snapshot": {"current_score": 0.79, "status": "hypothesis_only"},
    }), encoding="utf-8")
    scorecard_path.write_text(json.dumps({
        "updated_utc": "2026-05-08T00:00:00Z",
        "capabilities": {
            "tool_use_accuracy": {
                "current_score": 0.79,
                "previous_score": 0.79,
                "delta": 0.0,
                "confidence": 0.8,
                "evidence": [],
                "status": "hypothesis_only",
            }
        }
    }), encoding="utf-8")
    registry_path.write_text(json.dumps({
        "updated_utc": "2026-05-08T00:00:00Z",
        "status": "proposal_only",
        "proposals": [
            {
                "proposal_id": "PROP_EVAL",
                "semantic_key": "tool_use_accuracy:tool_routing",
                "current_state": "evaluation_pending",
                "allowed_next_states": ["candidate_promote", "rejected", "rolled_back"],
                "target_capability": "tool_use_accuracy",
                "risk_score": 0.5,
                "files_to_modify": ["a.py", "b.py"],
                "source_attribution": [
                    {"source_id": "github_a", "evidence_refs": [{"source_file": "README.snapshot.md"}, {"source_file": "tools.py"}]},
                    {"source_id": "github_b", "evidence_refs": [{"source_file": "session.py"}, {"source_file": "README.md"}]},
                ],
                "state_history": [{"state": "evaluation_pending", "ts_utc": "2026-05-08T00:00:00Z", "actor": "system", "reason": "ready"}],
                "sandbox_runs": [{
                    "run_id": "RUN_1",
                    "status": "evaluation_pending",
                    "manifest_path": str(manifest_path),
                    "rollback_manifest_path": str(rollback_path),
                    "evaluation_summary_path": str(summary_path),
                }],
            }
        ],
    }), encoding="utf-8")

    result = eval_mod.evaluate_proposal("PROP_EVAL", actor="tester", reason="eval_smoke")

    assert result["success"] is True
    assert result["evaluator_verdict"] == "evaluation_passed_candidate"
    assert result["metrics"]["before_after"]["capability_score_projected_after"] > result["metrics"]["before_after"]["capability_score_before"]
    assert result["proposal"]["current_state"] == "candidate_promote"
    assert Path(result["evaluation_report_path"]).exists()
    assert result["scorecard"]["capabilities"]["tool_use_accuracy"]["status"] == "candidate_ready"
    event_names = [name for name, _payload in events]
    assert "evaluation_completed" in event_names


@pytest.mark.unit
def test_capability_evaluator_needs_more_tests_when_targeted_regression_fails(monkeypatch, tmp_path):
    import brain_v9.learning.capability_evaluator as eval_mod
    import brain_v9.learning.proposal_governance as gov_mod

    registry_path = tmp_path / "proposal_registry_latest.json"
    scorecard_path = tmp_path / "capability_scorecard_latest.json"
    run_dir = tmp_path / "runs" / "RUN_2"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "sandbox_manifest.json"
    rollback_path = run_dir / "rollback_manifest.json"
    summary_path = run_dir / "evaluation_summary.json"

    monkeypatch.setattr(gov_mod, "PROPOSAL_REGISTRY_PATH", registry_path)
    monkeypatch.setattr(eval_mod, "CAPABILITY_SCORECARD_PATH", scorecard_path)
    monkeypatch.setattr(eval_mod, "_append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(eval_mod, "_targeted_regression", lambda _cap: {"ok": False, "tests": ["dummy"], "returncode": 1, "stdout_tail": "fail", "stderr_tail": ""})

    manifest_path.write_text(json.dumps({"copied_files": [{"status": "copied"}]}), encoding="utf-8")
    rollback_path.write_text(json.dumps({"files": [{"source_path": "a.py"}]}), encoding="utf-8")
    summary_path.write_text(json.dumps({
        "validation": {"py_compile": {"ok": True}},
        "production_integrity": {
            "before": [{"source_path": "a.py", "exists": True, "sha256": "1", "size_bytes": 1}],
            "after": [{"source_path": "a.py", "exists": True, "sha256": "1", "size_bytes": 1}],
        },
    }), encoding="utf-8")
    scorecard_path.write_text(json.dumps({
        "updated_utc": "2026-05-08T00:00:00Z",
        "capabilities": {
            "governance_quality": {
                "current_score": 0.79,
                "previous_score": 0.79,
                "delta": 0.0,
                "confidence": 0.8,
                "evidence": [],
                "status": "hypothesis_only",
            }
        }
    }), encoding="utf-8")
    registry_path.write_text(json.dumps({
        "updated_utc": "2026-05-08T00:00:00Z",
        "status": "proposal_only",
        "proposals": [
            {
                "proposal_id": "PROP_NEEDS_TESTS",
                "semantic_key": "governance_quality:regression_harness",
                "current_state": "evaluation_pending",
                "allowed_next_states": ["candidate_promote", "rejected", "rolled_back"],
                "target_capability": "governance_quality",
                "risk_score": 0.5,
                "evidence_strength_score": 0.79,
                "files_to_modify": ["a.py", "b.py"],
                "source_attribution": [{"source_id": "github_a", "evidence_refs": [{"source_file": "README.snapshot.md"}]}],
                "state_history": [{"state": "evaluation_pending", "ts_utc": "2026-05-08T00:00:00Z", "actor": "system", "reason": "ready"}],
                "sandbox_runs": [{
                    "run_id": "RUN_2",
                    "status": "evaluation_pending",
                    "manifest_path": str(manifest_path),
                    "rollback_manifest_path": str(rollback_path),
                    "evaluation_summary_path": str(summary_path),
                }],
            }
        ],
    }), encoding="utf-8")

    result = eval_mod.evaluate_proposal("PROP_NEEDS_TESTS", actor="tester", reason="eval_more_tests")

    assert result["success"] is True
    assert result["evaluator_verdict"] == "needs_more_tests"
    assert result["next_state"] is None
    assert result["proposal"]["current_state"] == "evaluation_pending"
