from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest

from ibkr_paper_30d.autonomy_workspace import WorkspaceViolation
from ibkr_paper_30d.research_sandbox import (
    MAX_ARGUMENT_BYTES,
    MAX_ARGUMENTS,
    WSLResearchSandbox,
)


REPO = Path(__file__).resolve().parents[2]


def _wsl_available() -> bool:
    if os.name != "nt":
        return False
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


class RecordingRunner:
    def __init__(self, payload: dict[str, Any], *, returncode: int = 0) -> None:
        self.payload = payload
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            self.returncode,
            stdout=json.dumps(self.payload).encode("utf-8"),
            stderr=b"",
        )


def _worker_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "schema": "RESEARCH_WORKER_RESULT_V1",
        "status": "COMPLETED",
        "returncode": 0,
        "stdout": "ok\n",
        "stderr": "",
        "resource_usage": {"cpu_seconds": 0.01},
        "failure_reason": None,
    }
    payload.update(overrides)
    return payload


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    for child in ("memory", "research", "tools", "datasets", "experiments"):
        (root / child).mkdir(parents=True, exist_ok=True)
    (root / "tools" / "probe.py").write_text("print('ok')\n", encoding="utf-8")
    return root


def test_host_broker_builds_a_fixed_wsl_command_and_minimal_environment(tmp_path: Path) -> None:
    runner = RecordingRunner(_worker_payload())
    sandbox = WSLResearchSandbox(repo_root=REPO, runner=runner)
    root = _workspace(tmp_path)

    receipt = sandbox.run(
        workspace_root=root,
        script_relative="tools/probe.py",
        arguments=("alpha", "two words"),
        timeout_seconds=12,
    )

    assert receipt["status"] == "COMPLETED"
    assert receipt["sandbox_mode"] == "WSL2_NAMESPACE_CHROOT_SECCOMP_V1"
    assert receipt["controls"]["network_namespace"] is True
    assert receipt["controls"]["seccomp"] is True
    command, kwargs = runner.calls[0]
    assert command[:8] == [
        "wsl.exe", "-d", "Ubuntu", "-u", "root", "--exec", "/bin/bash", command[7]
    ]
    assert receipt["controls"]["user_namespace"] is False
    assert receipt["controls"]["execution_uid"] == 65534
    assert command[-3:] == ["--", "alpha", "two words"]
    assert kwargs["env"] == {"SystemRoot": os.environ["SystemRoot"]}
    assert kwargs["shell"] is False


@pytest.mark.parametrize(
    "script_relative",
    ("../escape.py", "/tools/probe.py", "tools/../../escape.py", "C:/probe.py", "tools\\probe.py"),
)
def test_host_broker_rejects_noncanonical_script_paths(
    tmp_path: Path, script_relative: str
) -> None:
    sandbox = WSLResearchSandbox(repo_root=REPO, runner=RecordingRunner(_worker_payload()))
    with pytest.raises(WorkspaceViolation):
        sandbox.run(
            workspace_root=_workspace(tmp_path),
            script_relative=script_relative,
            arguments=(),
            timeout_seconds=5,
        )


def test_host_broker_rejects_unbounded_arguments(tmp_path: Path) -> None:
    sandbox = WSLResearchSandbox(repo_root=REPO, runner=RecordingRunner(_worker_payload()))
    root = _workspace(tmp_path)

    with pytest.raises(WorkspaceViolation, match="too many"):
        sandbox.run(
            workspace_root=root,
            script_relative="tools/probe.py",
            arguments=tuple("x" for _ in range(MAX_ARGUMENTS + 1)),
            timeout_seconds=5,
        )
    with pytest.raises(WorkspaceViolation, match="argument bytes"):
        sandbox.run(
            workspace_root=root,
            script_relative="tools/probe.py",
            arguments=("x" * (MAX_ARGUMENT_BYTES + 1),),
            timeout_seconds=5,
        )


def test_host_broker_fails_closed_when_wsl_cannot_start(tmp_path: Path) -> None:
    def unavailable(*_: Any, **__: Any) -> Any:
        raise FileNotFoundError("wsl.exe")

    sandbox = WSLResearchSandbox(repo_root=REPO, runner=unavailable)
    with pytest.raises(WorkspaceViolation, match="WSL2 research sandbox unavailable"):
        sandbox.run(
            workspace_root=_workspace(tmp_path),
            script_relative="tools/probe.py",
            arguments=(),
            timeout_seconds=5,
        )


def test_host_broker_bounds_untrusted_output_by_encoded_bytes(tmp_path: Path) -> None:
    runner = RecordingRunner(_worker_payload(stdout="x" * (600 * 1024)))
    sandbox = WSLResearchSandbox(repo_root=REPO, runner=runner)
    receipt = sandbox.run(
        workspace_root=_workspace(tmp_path),
        script_relative="tools/probe.py",
        arguments=(),
        timeout_seconds=5,
    )

    assert len(receipt["stdout"].encode("utf-8")) == 512 * 1024
    assert receipt["output_truncated"] is True


@pytest.mark.skipif(not _wsl_available(), reason="WSL2 Ubuntu unavailable")
def test_real_worker_timeout_returns_a_bounded_failure_receipt(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "tools" / "probe.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )

    receipt = WSLResearchSandbox(repo_root=REPO).run(
        workspace_root=root,
        script_relative="tools/probe.py",
        arguments=(),
        timeout_seconds=1,
    )

    assert receipt["status"] == "TIMEOUT"
    assert receipt["returncode"] in (124, 137)
    assert receipt["failure_reason"] == "SANDBOX_TIMEOUT"


@pytest.mark.skipif(not _wsl_available(), reason="WSL2 Ubuntu unavailable")
def test_real_worker_denies_host_files_network_processes_and_symlink_escape(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    (root / "tools" / "probe.py").write_text(
        textwrap.dedent(
            """
            import json
            import os
            import socket
            import subprocess
            from pathlib import Path

            result = {
                "mnt_c_exists": Path("/mnt/c").exists(),
                "owner_home_exists": Path("/home").exists(),
                "visible_root": sorted(item.name for item in Path("/").iterdir()),
                "sensitive_env": sorted(
                    key for key in os.environ
                    if any(word in key.upper() for word in
                           ("IBKR", "TOKEN", "SECRET", "PASSWORD", "CODEX_HOME"))
                ),
            }
            try:
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result["socket"] = "ALLOWED"
            except OSError as exc:
                result["socket"] = f"DENIED:{exc.errno}"
            try:
                subprocess.run(["/usr/bin/id"], check=False)
                result["process"] = "ALLOWED"
            except OSError as exc:
                result["process"] = f"DENIED:{exc.errno}"
            link = Path("/workspace/experiments/host-link")
            link.symlink_to("/mnt/c/Windows/win.ini")
            try:
                link.read_text(encoding="utf-8")
                result["symlink_escape"] = "ALLOWED"
            except OSError:
                result["symlink_escape"] = "DENIED"
            artifact = Path("/workspace/experiments/generated.json")
            artifact.write_text(json.dumps({"sandboxed": True}), encoding="utf-8")
            print(json.dumps(result, sort_keys=True))
            """
        ),
        encoding="utf-8",
    )

    receipt = WSLResearchSandbox(repo_root=REPO).run(
        workspace_root=root,
        script_relative="tools/probe.py",
        arguments=(),
        timeout_seconds=20,
    )

    assert receipt["status"] == "COMPLETED", receipt
    probe = json.loads(receipt["stdout"])
    assert probe["mnt_c_exists"] is False
    assert probe["owner_home_exists"] is False
    assert probe["sensitive_env"] == []
    assert probe["socket"].startswith("DENIED:")
    assert probe["process"].startswith("DENIED:")
    assert probe["symlink_escape"] == "DENIED"
    assert set(probe["visible_root"]) <= {
        "bin", "lib", "lib64", "proc", "sbin", "scratch", "usr", "worker", "workspace"
    }
    generated = {item["path"]: item for item in receipt["generated_artifacts"]}
    assert generated["experiments/generated.json"]["operation"] == "CREATED"
    assert len(generated["experiments/generated.json"]["sha256"]) == 64
