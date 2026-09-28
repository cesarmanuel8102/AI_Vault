from __future__ import annotations

from ibkr_paper_30d.autonomous_research import (
    AutonomousTurn,
    AutonomousTurnMode,
    CodexAutonomousCLIProvider,
    ResearchResult,
)
from ibkr_paper_30d.autonomous_runtime import run_autonomous_cycle
from ibkr_paper_30d.autonomy_bootstrap import (
    MAX_BOOTSTRAP_BYTES,
    MAX_DECISIONS,
    MAX_WORKSPACE_ARTIFACTS,
    AutonomyBootstrapBuilder,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle
from ibkr_paper_30d.types import new_uuid7

NOW = "2026-09-28T14:00:00Z"


def _bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-bootstrap",
        utc_timestamp=NOW,
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS", "account": "DU-SHOULD-NOT-LEAK"},
        experiment_subledger_snapshot={
            "allocation": "500",
            "cash": "475",
            "equity": "500",
        },
        broker_account_snapshot={
            "paper_account": True,
            "declared_options_level": 4,
            "account": "DU-SHOULD-NOT-LEAK",
        },
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={
            "gate_status": "PASS",
            "policy_version": "MARKET_DATA_POLICY_V1",
        },
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
        experiment_clock={
            "epoch_state": "ACTIVE",
            "epoch_id": "AUTONOMY_EPOCH_1",
            "start_utc": "2026-09-28T13:30:00Z",
            "end_utc": "2026-10-28T13:30:00Z",
            "remaining_days": 29.979,
            "remaining_seconds": 2_590_200,
            "definition_sha256": "d" * 64,
            "clock_event_sha256": "c" * 64,
        },
    )


class Workspace:
    def __init__(self, artifacts=None, contents=None):
        self._artifacts = list(artifacts or [])
        self._contents = dict(contents or {})

    def summary(self, *, max_artifacts=40):
        return {
            "artifact_count": len(self._artifacts),
            "recent_artifacts": self._artifacts[-max_artifacts:],
            "registry_events": len(self._artifacts),
        }

    def read_artifact(self, path):
        content = self._contents[path]
        return {
            "path": path,
            "content": content,
            "sha256": sha256_json({"content": content}),
            "size_bytes": len(content.encode("utf-8")),
        }


class QuantConnect:
    def execute(self, arguments):
        assert arguments == {"operation": "STATUS"}
        return {
            "status": "OPTIONAL_UNAVAILABLE",
            "required": False,
            "reason": "LEAN_CLI_UNAVAILABLE",
        }


class Toolbox:
    def __init__(self, workspace=None):
        self.workspace = workspace
        self.quantconnect = QuantConnect()

    def manifest(self):
        return [
            {"tool": "WORKSPACE", "purpose": "persistent research"},
            {"tool": "RUN_RESEARCH_SCRIPT", "purpose": "isolated computation"},
        ]

    def workspace_summary(self):
        return None if self.workspace is None else self.workspace.summary()

    def execute(self, request, bundle):
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=False,
            data={},
            error="not_expected",
        )

    def validate_proposal(self, proposal, bundle):
        raise AssertionError("not expected")


def _append_final(db: Database, index: int, *, malformed: bool = False) -> None:
    payload = {
        "decision_cycle_id": f"cycle-{index:03d}",
        "accepted": True,
        "decision": "NO_TRADE",
        "proposal": None,
        "reason_codes": [f"REASON_{index:03d}"],
    }
    encoded = canonical_bytes(payload).decode("utf-8")
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            str(new_uuid7()),
            payload["decision_cycle_id"],
            f"inv-{index:03d}",
            1,
            "final_outcome",
            "{" if malformed else encoded,
            "0" * 64 if malformed else sha256_json(payload),
            f"2026-09-{index + 1:02d}T14:00:00Z",
        ),
    )


def test_empty_bootstrap_has_exact_authority_and_epoch_fields(tmp_path) -> None:
    with Database.open(tmp_path / "bootstrap.sqlite3") as db:
        builder = AutonomyBootstrapBuilder(db)
        first = builder.build(bundle=_bundle(), toolbox=Toolbox(), execute_paper=False)
        second = builder.build(bundle=_bundle(), toolbox=Toolbox(), execute_paper=False)

    assert first == second
    assert set(first) == {
        "schema",
        "trust_boundary",
        "epoch",
        "remaining_horizon",
        "permissions",
        "constraints",
        "paper_identity",
        "current_state",
        "tools",
        "quantconnect",
        "continuity",
    }
    assert first["epoch"]["epoch_id"] == "AUTONOMY_EPOCH_1"
    assert first["epoch"]["definition_sha256"] == "d" * 64
    assert first["epoch"]["clock_event_sha256"] == "c" * 64
    assert first["remaining_horizon"]["remaining_days"] == 29.979
    assert first["permissions"] == {
        "research_authority": "HOST_MEDIATED_ONLY",
        "order_authority": "DISABLED",
        "workspace_persistence": True,
        "self_tooling": "ISOLATED_RESEARCH_WORKER_ONLY",
    }
    assert first["paper_identity"]["class"] == "IBKR_PAPER"
    assert first["continuity"]["recent_accepted_decisions"] == []
    assert first["continuity"]["recent_workspace_artifacts"] == []
    assert b"DU-SHOULD-NOT-LEAK" not in canonical_bytes(first)


def test_bootstrap_bounds_records_bytes_and_ignores_malformed_history(tmp_path) -> None:
    large = "x" * 50_000
    artifacts = [
        {
            "path": f"notes/research-{index:03d}.md",
            "sha256": f"{index:064x}",
            "size_bytes": len(large),
            "created_at_utc": f"2026-09-{index + 1:02d}T15:00:00Z",
            "created_by_cycle": f"cycle-{index:03d}",
        }
        for index in range(20)
    ]
    workspace = Workspace(artifacts, {item["path"]: large for item in artifacts})
    with Database.open(tmp_path / "bootstrap.sqlite3") as db:
        for index in range(20):
            _append_final(db, index)
        _append_final(db, 20, malformed=True)
        value = AutonomyBootstrapBuilder(db).build(
            bundle=_bundle(), toolbox=Toolbox(workspace), execute_paper=False
        )

    continuity = value["continuity"]
    assert len(continuity["recent_accepted_decisions"]) == MAX_DECISIONS
    assert len(continuity["recent_workspace_artifacts"]) <= MAX_WORKSPACE_ARTIFACTS
    assert continuity["ignored_malformed_records"] == 1
    assert len(canonical_bytes(value)) <= MAX_BOOTSTRAP_BYTES
    assert (
        continuity["recent_accepted_decisions"][-1]["decision_cycle_id"] == "cycle-019"
    )


def test_workspace_continuity_is_untrusted_and_excludes_audit_documents(
    tmp_path,
) -> None:
    artifacts = [
        {"path": "hypotheses/volatility.md", "sha256": "1" * 64, "size_bytes": 8},
        {"path": "questions/open.md", "sha256": "2" * 64, "size_bytes": 9},
        {"path": "audit/external-review.md", "sha256": "3" * 64, "size_bytes": 11},
        {"path": "development/internal-plan.md", "sha256": "4" * 64, "size_bytes": 12},
    ]
    contents = {
        "hypotheses/volatility.md": "vol edge",
        "questions/open.md": "why now?",
        "audit/external-review.md": "AUDIT LEAK",
        "development/internal-plan.md": "DEV LEAK",
    }
    with Database.open(tmp_path / "bootstrap.sqlite3") as db:
        value = AutonomyBootstrapBuilder(db).build(
            bundle=_bundle(),
            toolbox=Toolbox(Workspace(artifacts, contents)),
            execute_paper=False,
        )

    continuity = value["continuity"]
    assert continuity["hypotheses"][0]["content"] == "vol edge"
    assert continuity["unresolved_questions"][0]["content"] == "why now?"
    assert all(
        item["trust"] == "UNTRUSTED_MODEL_AUTHORED"
        for item in continuity["recent_workspace_artifacts"]
    )
    encoded = canonical_bytes(value)
    assert b"AUDIT LEAK" not in encoded
    assert b"DEV LEAK" not in encoded
    assert b"external-review" not in encoded


class CapturingProvider:
    last_native_tool_events = []

    def __init__(self):
        self.bootstraps = []

    def install_first_process_bootstrap(self, value):
        self.bootstraps.append(value)

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.NO_TRADE,
            proposal=None,
            confidence="0.8",
            reasoning_summary="No qualified edge.",
            reason_codes=["NO_EDGE"],
        )


def test_runtime_installs_bootstrap_only_for_first_process_invocation(tmp_path) -> None:
    provider = CapturingProvider()
    with Database.open(tmp_path / "bootstrap.sqlite3") as db:
        run_autonomous_cycle(
            _bundle(), database=db, provider=provider, toolbox=Toolbox()
        )
        second = _bundle().model_copy(update={"decision_cycle_id": "cycle-bootstrap-2"})
        run_autonomous_cycle(second, database=db, provider=provider, toolbox=Toolbox())

    assert len(provider.bootstraps) == 1
    assert provider.bootstraps[0]["schema"] == "AUTONOMY_FIRST_PROCESS_BOOTSTRAP_V1"


def test_codex_provider_consumes_bootstrap_exactly_once() -> None:
    provider = CodexAutonomousCLIProvider(runner=lambda *args, **kwargs: None)
    bootstrap = {"schema": "AUTONOMY_FIRST_PROCESS_BOOTSTRAP_V1"}

    provider.install_first_process_bootstrap(bootstrap)

    assert provider._take_first_process_bootstrap() == bootstrap
    assert provider._take_first_process_bootstrap() is None
