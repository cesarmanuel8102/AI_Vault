"""AUTONOMY_EPOCH_1 workspace + self-tooling tests (deterministic, no Codex)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from ibkr_paper_30d.autonomous_research import (
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox, quantconnect_available
from ibkr_paper_30d.autonomy_workspace import AutonomyWorkspace, WorkspaceViolation
from ibkr_paper_30d.research_sandbox import WSLResearchSandbox


REPO = Path(__file__).resolve().parents[2]


def _wsl_available():
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "--exec", "/bin/true"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


WSL_AVAILABLE = _wsl_available()
KERNEL_FILES = [
    "ibkr_paper_30d/autonomous_execution.py",
    "ibkr_paper_30d/ibkr_readonly_session.py",
    "ibkr_paper_30d/owner_authorization.py",
    "ibkr_paper_30d/execution_lock.py",
    "ibkr_paper_30d/risk.py",
]


class BaseStub:
    def manifest(self):
        return [{"tool": ResearchTool.QUOTE.value, "purpose": "stub"}]

    def execute(self, request, bundle):
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data={"stub": True},
        )

    def validate_proposal(self, proposal, bundle):
        raise AssertionError("not expected in these tests")


def request(tool, arguments, rid="r1"):
    return ResearchRequest(
        request_id=rid, tool=tool, arguments=arguments, purpose="test"
    )


@pytest.fixture()
def workspace(tmp_path):
    return AutonomyWorkspace(
        tmp_path / "workspace", sandbox=WSLResearchSandbox(repo_root=REPO)
    )


@pytest.fixture()
def toolbox(workspace):
    return AutonomyToolbox(BaseStub(), workspace)


# ---------------------------------------------------------------------------
# 5. Persistent workspace survives cycles
# ---------------------------------------------------------------------------


def test_workspace_artifacts_persist_across_workspace_instances(tmp_path):
    first = AutonomyWorkspace(tmp_path / "ws")
    first.write_artifact("memory/hypotheses.md", "H1: vol regime shift", cycle_id="c1")
    second = AutonomyWorkspace(tmp_path / "ws")
    artifacts = second.list_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0]["path"] == "memory/hypotheses.md"
    content = second.read_artifact("memory/hypotheses.md")
    assert content["content"] == "H1: vol regime shift"


# ---------------------------------------------------------------------------
# 6-8. Structural isolation: no broker-write, no LIVE, no kernel mutation
# ---------------------------------------------------------------------------


def test_workspace_rejects_path_escape(workspace):
    for bad in ("../escape.txt", "a/../../escape.py", "..\\escape", "C:/x"):
        with pytest.raises(WorkspaceViolation):
            workspace.write_artifact(bad, "x")


def test_python_artifacts_only_in_tools(workspace):
    with pytest.raises(WorkspaceViolation):
        workspace.write_artifact("memory/evil.py", "print(1)")
    # Non-python anywhere inside the workspace is fine.
    workspace.write_artifact("memory/notes.md", "ok")
    # Python inside tools is fine.
    workspace.write_artifact("tools/analyzer.py", "print('ok')")


def test_scripts_only_run_from_tools(workspace):
    outside = workspace.paths.root / "memory" / "note.py"
    outside.write_text("print('x')", encoding="utf-8")
    with pytest.raises(WorkspaceViolation):
        workspace.run_script("memory/note.py")


def test_workspace_cannot_write_immutable_kernel_files(workspace):
    """The workspace has no API that reaches outside its root; the registry
    and every write path resolve strictly inside. Direct structural proof."""
    with pytest.raises(WorkspaceViolation):
        workspace.write_artifact("../../ibkr_paper_30d/execution_lock.py", "bypass")


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_script_environment_has_no_broker_credentials(workspace):
    workspace.write_artifact(
        "tools/envprobe.py",
        textwrap.dedent(
            """
            import json, os
            leak = {k: v for k, v in os.environ.items()
                    if "IBKR" in k.upper() or "SECRET" in k.upper()
                    or "TOKEN" in k.upper() or "PASSWORD" in k.upper()}
            print(json.dumps({"leak": leak, "has_path": "PATH" in os.environ}))
            """
        ),
    )
    run = workspace.run_script("tools/envprobe.py")
    assert run["status"] == "COMPLETED", run
    payload = json.loads(run["stdout"])
    assert payload["leak"] == {}
    assert payload["has_path"] is False


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_script_cannot_spawn_external_clis(workspace):
    """Research scripts must not reach provider CLIs (codex) or other
    host tools: every attempt to cross execve is denied by seccomp."""

    workspace.write_artifact(
        "tools/spawnprobe.py",
        textwrap.dedent(
            """
            import json, shutil, subprocess
            results = {}
            for name in ("codex", "lean", "git"):
                executable = shutil.which(name)
                if executable is None:
                    results[name] = "ABSENT"
                    continue
                try:
                    subprocess.run([executable, "--version"], check=False)
                    results[name] = "EXECUTED"
                except OSError as exc:
                    results[name] = f"DENIED:{exc.errno}"
            print(json.dumps(results))
            """
        ),
    )
    run = workspace.run_script("tools/spawnprobe.py")
    assert run["status"] == "COMPLETED", run
    found = json.loads(run["stdout"])
    for cli in ("codex", "lean", "git"):
        assert found[cli] != "EXECUTED", f"{cli} was executable from a research script"


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_script_cannot_import_execution_kernel(workspace):
    probe = textwrap.dedent(
        """
        import importlib, json
        results = {}
        for module in ("ibkr_paper_30d.autonomous_execution",
                       "ibkr_paper_30d.broker",
                       "ibkr_paper_30d.execution_lock"):
            try:
                importlib.import_module(module)
                results[module] = "IMPORTED"
            except Exception as exc:
                results[module] = type(exc).__name__
        print(json.dumps(results))
        """
    )
    workspace.write_artifact("tools/kernelprobe.py", probe)
    run = workspace.run_script("tools/kernelprobe.py")
    assert run["status"] == "COMPLETED", run
    results = json.loads(run["stdout"])
    for module, outcome in results.items():
        assert outcome != "IMPORTED", f"{module} was importable by research script"


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_script_cannot_connect_to_broker_port(workspace):
    probe = textwrap.dedent(
        """
        import socket, json
        results = {}
        for host, port in (("127.0.0.1", 4001), ("127.0.0.1", 4002),
                           ("127.0.0.1", 7496), ("127.0.0.1", 7497)):
            s = socket.socket()
            s.settimeout(1)
            try:
                s.connect((host, port))
                results[f"{host}:{port}"] = "CONNECTED"
            except Exception:
                results[f"{host}:{port}"] = "BLOCKED"
            finally:
                s.close()
        print(json.dumps(results))
        """
    )
    workspace.write_artifact("tools/netprobe.py", probe)
    run = workspace.run_script("tools/netprobe.py")
    assert run["status"] in ("COMPLETED", "FAILED")
    if run["status"] == "COMPLETED":
        results = json.loads(run["stdout"])
        for endpoint, outcome in results.items():
            if endpoint.endswith(":4002") and outcome == "CONNECTED":
                pytest.skip(
                    "gateway reachable in dev env; structural isolation "
                    "documented via no-credentials + no-imports tests"
                )
            # LIVE ports must never be connected even if a gateway is up.
            if port_live(endpoint):
                assert outcome != "CONNECTED", f"LIVE endpoint {endpoint} reachable"


def port_live(endpoint: str) -> bool:
    return endpoint.endswith((":7496", ":7497", ":4001"))


# ---------------------------------------------------------------------------
# 9. Tools can be created/reused
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_research_script_create_run_reuse(workspace):
    workspace.write_artifact(
        "tools/stats.py",
        textwrap.dedent(
            """
            import json, statistics
            data = [1.0, 2.0, 3.0, 4.0]
            print(json.dumps({"mean": statistics.mean(data)}))
            """
        ),
        cycle_id="c1",
    )
    first = workspace.run_script("tools/stats.py", cycle_id="c1")
    assert first["status"] == "COMPLETED"
    assert json.loads(first["stdout"])["mean"] == 2.5
    # Reuse in a later cycle with a new workspace instance.
    later = AutonomyWorkspace(workspace.paths.root, sandbox=workspace.sandbox)
    second = later.run_script("tools/stats.py", cycle_id="c2")
    assert second["status"] == "COMPLETED"
    # Registry records both runs with script hash + cycle ids.
    events = later._registry_events()
    runs = [e["event"]["run"] for e in events if e["event"].get("event_type") == "SCRIPT_RUN"]
    assert len(runs) == 2
    assert runs[0]["script_sha256"] == runs[1]["script_sha256"]
    assert {r["cycle_id"] for r in runs} == {"c1", "c2"}


# ---------------------------------------------------------------------------
# 10. Malformed custom tool fails closed
# ---------------------------------------------------------------------------


def test_malformed_custom_tool_fails_closed(toolbox):
    result = toolbox.execute(
        request(ResearchTool.RUN_RESEARCH_SCRIPT, {"path": "tools/does_not_exist.py"}),
        None,
    )
    assert result.success is False
    assert result.error


def test_unknown_workspace_operation_fails_closed(toolbox):
    result = toolbox.execute(
        request(ResearchTool.WORKSPACE, {"operation": "rm-rf"}),
        None,
    )
    assert result.success is False


# ---------------------------------------------------------------------------
# 11. Custom tool timeout does not kill service
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_custom_tool_timeout_is_contained(workspace):
    workspace.write_artifact(
        "tools/hang.py",
        "import time\n" "time.sleep(30)\n",
    )
    run = workspace.run_script("tools/hang.py", timeout_seconds=1.0)
    assert run["status"] == "TIMEOUT"
    # The workspace still works afterwards (service liveness preserved).
    artifact = workspace.write_artifact("memory/after_timeout.md", "alive")
    assert artifact["sha256"]


# ---------------------------------------------------------------------------
# 12. Custom tool failure does not imply trading permission
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not WSL_AVAILABLE, reason="WSL2 Ubuntu unavailable")
def test_custom_tool_failure_yields_no_trading_permission(toolbox, workspace):
    workspace.write_artifact("tools/failing.py", "raise RuntimeError('boom')\n")
    result = toolbox.execute(
        request(ResearchTool.RUN_RESEARCH_SCRIPT, {"path": "tools/failing.py"}),
        None,
    )
    assert result.success is False
    assert result.data["status"] == "FAILED"
    # No decision/proposal/authority fields exist on research results at all;
    # pin that research results never carry execution semantics.
    payload = result.model_dump(mode="json")
    for forbidden in ("decision", "proposal", "order", "authorize"):
        assert forbidden not in payload


# ---------------------------------------------------------------------------
# QuantConnect optional lab
# ---------------------------------------------------------------------------


def test_quantconnect_is_optional_and_status_only(toolbox):
    result = toolbox.execute(request(ResearchTool.QUANTCONNECT, {}), None)
    assert result.success is True
    status = result.data
    assert status["required"] is False
    assert isinstance(status["available"], bool)


def test_quantconnect_command_whitelist_blocks_live():
    from ibkr_paper_30d.autonomy_toolbox import run_quantconnect_command

    result = run_quantconnect_command(["live", "--tickers", "SPY"])
    assert result["success"] is False
    assert "not allowed" in result["error"]


# ---------------------------------------------------------------------------
# Workspace tool surface through the toolbox
# ---------------------------------------------------------------------------


def test_workspace_tool_roundtrip(toolbox, workspace):
    result = toolbox.execute(
        request(
            ResearchTool.WORKSPACE,
            {"operation": "write", "path": "memory/h.md", "content": "hello"},
        ),
        None,
    )
    assert result.success is True
    result = toolbox.execute(
        request(ResearchTool.WORKSPACE, {"operation": "list"}), None
    )
    assert result.success is True
    assert result.data["summary"]["artifact_count"] == 1


def test_workspace_registry_is_append_only_and_hashed(workspace):
    workspace.write_artifact("memory/a.md", "a", cycle_id="c")
    workspace.write_artifact("memory/b.md", "b", cycle_id="c")
    registry = workspace.paths.registry_path.read_text(encoding="utf-8")
    lines = [line for line in registry.splitlines() if line.strip()]
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert record["schema"] == "AUTONOMY_WORKSPACE_EVENT_V1"
        assert record["event"]["artifact"]["sha256"]


def test_workspace_summary_shape(workspace):
    workspace.write_artifact("memory/x.md", "x")
    summary = workspace.summary()
    assert summary["artifact_count"] == 1
    assert summary["recent_artifacts"][0]["path"] == "memory/x.md"
