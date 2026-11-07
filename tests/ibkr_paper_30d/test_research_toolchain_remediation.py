"""Research toolchain remediation: bindings, structured errors, data transport and HOME."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ibkr_paper_30d.autonomous_research import ResearchRequest, ResearchResult, ResearchTool
from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox, QuantConnectMediator
from ibkr_paper_30d.autonomy_workspace import AutonomyWorkspace


class BaseStub:
    def manifest(self):
        return []

    def execute(self, request, bundle):
        raise AssertionError("base toolbox must not receive capability requests")


class FakeSandbox:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, *, workspace_root, script_relative, arguments, timeout_seconds):
        self.calls.append(
            {"script": script_relative, "arguments": tuple(arguments), "timeout": timeout_seconds}
        )
        return {"status": "COMPLETED", "returncode": 0, "stdout": "ok", "stderr": "",
                "generated_artifacts": []}


@pytest.fixture()
def sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture()
def toolbox(tmp_path, sandbox) -> AutonomyToolbox:
    workspace = AutonomyWorkspace(tmp_path / "workspace", sandbox=sandbox)
    return AutonomyToolbox(BaseStub(), workspace)


def _req(tool: ResearchTool, arguments: dict[str, Any], rid: str = "r1") -> ResearchRequest:
    return ResearchRequest(request_id=rid, tool=tool, arguments=arguments, purpose="test")


def _history_with(rid: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "round": 1,
        "type": "research_result",
        "payload": ResearchResult(
            request_id=rid, tool=ResearchTool.HISTORICAL_BARS, success=True, data=data
        ).model_dump(mode="json"),
    }]


def test_workspace_action_alias_is_honoured_instead_of_silently_listing(toolbox) -> None:
    written = toolbox.execute(
        _req(ResearchTool.WORKSPACE, {"action": "CREATE", "path": "tools/a.py", "content": "print(1)"}),
        None,
    )
    read = toolbox.execute(_req(ResearchTool.WORKSPACE, {"action": "READ", "path": "tools/a.py"}), None)

    assert written.success is True
    assert written.data["artifact"]["path"] == "tools/a.py"
    assert read.success is True
    assert read.data["content"] == "print(1)"


def test_workspace_read_by_artifact_id(toolbox) -> None:
    written = toolbox.execute(
        _req(ResearchTool.WORKSPACE, {"operation": "write", "path": "memory/n.md", "content": "x"}), None
    )
    artifact_id = written.data["artifact"]["artifact_id"]

    read = toolbox.execute(_req(ResearchTool.WORKSPACE, {"action": "read", "artifact_id": artifact_id}), None)

    assert read.success is True
    assert read.data["content"] == "x"


def test_unknown_workspace_operation_returns_structured_error_with_valid_operations(toolbox) -> None:
    result = toolbox.execute(_req(ResearchTool.WORKSPACE, {"operation": "teleport"}), None)

    assert result.success is False
    assert result.data["tool"] == "WORKSPACE"
    assert result.data["error_type"] == "UNSUPPORTED_OPERATION"
    assert result.data["retryable"] is False
    assert "write" in result.data["valid_operations"]
    assert result.data["corrective_hint"]


def test_conflicting_operation_aliases_are_rejected(toolbox) -> None:
    result = toolbox.execute(_req(ResearchTool.WORKSPACE, {"operation": "read", "action": "write"}), None)

    assert result.success is False
    assert result.data["error_type"] == "CONFLICTING_ARGUMENTS"


def test_run_research_script_accepts_script_path_and_args_aliases(toolbox, sandbox) -> None:
    toolbox.execute(
        _req(ResearchTool.WORKSPACE, {"operation": "write", "path": "tools/s.py", "content": "print(1)"}), None
    )

    result = toolbox.execute(
        _req(ResearchTool.RUN_RESEARCH_SCRIPT, {"script_path": "tools/s.py", "args": ["--self-test"]}), None
    )

    assert result.success is True, result.data
    assert sandbox.calls[-1]["arguments"] == ("--self-test",)


def test_run_research_script_rejects_unsupported_keys_instead_of_ignoring_them(toolbox, sandbox) -> None:
    toolbox.execute(
        _req(ResearchTool.WORKSPACE, {"operation": "write", "path": "tools/s.py", "content": "print(1)"}), None
    )

    result = toolbox.execute(
        _req(ResearchTool.RUN_RESEARCH_SCRIPT, {"path": "tools/s.py", "stdin": "{}"}), None
    )

    assert result.success is False
    assert result.data["error_type"] == "UNSUPPORTED_ARGUMENTS"
    assert result.data["unsupported_arguments"] == ["stdin"]
    assert "input_request_ids" in result.data["corrective_hint"]
    assert sandbox.calls == []


def test_run_research_script_missing_path_is_structured_not_keyerror(toolbox) -> None:
    result = toolbox.execute(_req(ResearchTool.RUN_RESEARCH_SCRIPT, {"arguments": []}), None)

    assert result.success is False
    assert result.error != "KeyError:'path'"
    assert result.data["error_type"] == "MISSING_ARGUMENT"


def test_run_research_script_transports_prior_research_results_as_files(toolbox, sandbox, tmp_path) -> None:
    toolbox.execute(
        _req(ResearchTool.WORKSPACE, {"operation": "write", "path": "tools/s.py", "content": "print(1)"}), None
    )
    bars = {"bars": [{"close": 1.0}, {"close": 2.0}]}

    result = toolbox.execute_with_history(
        _req(ResearchTool.RUN_RESEARCH_SCRIPT,
             {"path": "tools/s.py", "arguments": ["--mode", "x"], "input_request_ids": ["r1-btc-bars"]},
             rid="r2"),
        None,
        _history_with("r1-btc-bars", bars),
    )

    assert result.success is True, result.data
    arguments = sandbox.calls[-1]["arguments"]
    assert arguments[:2] == ("--mode", "x")
    assert arguments[2] == "/workspace/datasets/research_inputs/r1-btc-bars.json"
    stored = tmp_path / "workspace" / "datasets" / "research_inputs" / "r1-btc-bars.json"
    assert json.loads(stored.read_text(encoding="utf-8")) == bars


def test_run_research_script_reports_unknown_input_request(toolbox, sandbox) -> None:
    toolbox.execute(
        _req(ResearchTool.WORKSPACE, {"operation": "write", "path": "tools/s.py", "content": "print(1)"}), None
    )

    result = toolbox.execute_with_history(
        _req(ResearchTool.RUN_RESEARCH_SCRIPT, {"path": "tools/s.py", "input_request_ids": ["missing"]}),
        None,
        [],
    )

    assert result.success is False
    assert result.data["error_type"] == "INPUT_RESULT_NOT_FOUND"
    assert sandbox.calls == []


def test_workspace_write_from_research_result_with_json_pointer(toolbox, tmp_path) -> None:
    result = toolbox.execute_with_history(
        _req(ResearchTool.WORKSPACE, {"action": "CREATE_FROM_RESEARCH_RESULT",
                                      "path": "research/bars.json", "source_request_id": "r1",
                                      "json_pointer": "/data/bars"}),
        None,
        _history_with("r1", {"bars": [1, 2, 3]}),
    )

    assert result.success is True, result.data
    stored = tmp_path / "workspace" / "research" / "bars.json"
    assert json.loads(stored.read_text(encoding="utf-8")) == [1, 2, 3]


def test_identical_non_retryable_failure_is_not_executed_again(toolbox) -> None:
    first = toolbox.execute(_req(ResearchTool.WORKSPACE, {"operation": "teleport"}), None)
    second = toolbox.execute(_req(ResearchTool.WORKSPACE, {"operation": "teleport"}, rid="r2"), None)

    assert first.data["error_type"] == "UNSUPPORTED_OPERATION"
    assert second.success is False
    assert second.data["error_type"] == "IDENTICAL_NON_RETRYABLE_REQUEST_REPEATED"


def test_quantconnect_action_alias_and_isolated_home(tmp_path) -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="lean 1.0", stderr="")

    mediator = QuantConnectMediator(
        workspace_root=tmp_path / "workspace", executable="lean.exe", runner=runner
    )

    result = mediator.execute({"action": "STATUS"})

    assert result["status"] == "RUNTIME_AVAILABLE"
    env = calls[0]["env"]
    assert env["HOME"] == env["USERPROFILE"]
    home = Path(env["HOME"])
    assert home.is_dir()
    assert (tmp_path / "workspace").resolve() not in home.resolve().parents
    assert str(Path.home()) != env["HOME"]


def test_manifest_documents_bindings_and_valid_operations(toolbox) -> None:
    manifest = {item["tool"]: item for item in toolbox.manifest()}

    assert "valid_operations" in manifest["WORKSPACE"]
    assert "write_from_research_result" in manifest["WORKSPACE"]["valid_operations"]
    assert set(manifest["RUN_RESEARCH_SCRIPT"]["arguments"]) >= {
        "path", "arguments", "timeout_seconds", "input_request_ids"
    }
    assert set(manifest["QUANTCONNECT"]["valid_operations"]) == {
        "STATUS", "LIST_LOCAL_PROJECTS", "RUN_LOCAL_BACKTEST"
    }


def test_research_loop_routes_capability_requests_through_history(monkeypatch) -> None:
    import inspect

    from ibkr_paper_30d.autonomous_research import AutonomousResearchLoop

    source = inspect.getsource(AutonomousResearchLoop.run)

    assert "execute_with_history" in source
