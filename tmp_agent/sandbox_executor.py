# sandbox_executor.py
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Root del sandbox (auto)
SANDBOX_ROOT = Path(__file__).resolve().parent
from typing import Any, Dict, List, Optional

from policies import SandboxPolicy


@dataclass
class ExecResult:
    ok: bool
    action: str
    detail: str
    data: Dict[str, Any]


class SandboxExecutor:
    """
    Executor controlado para Dev Sandbox.

    Acciones soportadas (allowlist):
      - list_dir
      - read_text
      - write_text
      - append_text
      - run_cmd (muy restringido: solo prefijos permitidos)
    """

    def __init__(self, policy: Optional[SandboxPolicy] = None):
        self.policy = policy or SandboxPolicy.default()

        # Allowlist de comandos (prefijos). Minimalista a propósito.
        self.allowed_cmd_prefixes: List[List[str]] = [
            ["python", "--version"],
            ["python", "-m", "py_compile"],
            ["python", "-m", "pytest"],
        ]
    def _is_cmd_allowed(self, cmd: List[str]) -> bool:
        # Strict allowlist (robust):
        #   A) python -m py_compile <files...>
        #   B) python <SANDBOX_ROOT>\smoke_runner.py
        # Supports python being a full path, and optional cmd.exe wrapper.
        if not cmd:
            return False

        def _is_python_token(tok: str) -> bool:
            try:
                name = Path(tok).name.lower()
            except Exception:
                name = (tok or "").lower()
            return name in ("python", "python.exe")

        # Handle optional wrapper: cmd.exe /c python ...
        i0 = 0
        if len(cmd) >= 3:
            try:
                n0 = Path(cmd[0]).name.lower()
            except Exception:
                n0 = (cmd[0] or "").lower()
            if n0 in ("cmd.exe", "cmd") and (cmd[1] or "").lower() == "/c":
                i0 = 2  # python is at cmd[2]

        if i0 >= len(cmd):
            return False

        if not _is_python_token(cmd[i0]):
            return False

        # Allow: python -m py_compile ...
        if len(cmd) >= (i0 + 3) and cmd[i0 + 1] == "-m" and cmd[i0 + 2] == "py_compile":
            return True

        # Allow: python smoke_runner.py (exact path)
        try:
            runner = (SANDBOX_ROOT / "smoke_runner.py").resolve()
            if len(cmd) >= (i0 + 2):
                arg1 = str(cmd[i0 + 1]).strip('"').strip("'")
                if str(Path(arg1).resolve()).lower() == str(runner).lower():
                    return True
        except Exception:
            return False

        return False

    def list_dir(self, path: str) -> ExecResult:
        p = Path(path)
        self.policy.assert_can_read(p)
        if not p.exists():
            return ExecResult(False, "list_dir", "PATH_NOT_FOUND", {"path": str(p)})
        if not p.is_dir():
            return ExecResult(False, "list_dir", "NOT_A_DIRECTORY", {"path": str(p)})

        items = []
        for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            try:
                st = child.stat()
                items.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "is_dir": child.is_dir(),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
                )
            except Exception as e:
                items.append({"name": child.name, "path": str(child), "error": str(e)})

        return ExecResult(True, "list_dir", "OK", {"path": str(p), "items": items})

    def read_text(self, path: str, max_bytes: int = 2_000_000) -> ExecResult:
        p = Path(path)
        self.policy.assert_can_read(p)
        if not p.exists():
            return ExecResult(False, "read_text", "PATH_NOT_FOUND", {"path": str(p)})

        data = p.read_bytes()
        if len(data) > max_bytes:
            return ExecResult(False, "read_text", "FILE_TOO_LARGE", {"path": str(p), "size": len(data)})

        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("utf-8", errors="replace")

        return ExecResult(True, "read_text", "OK", {"path": str(p), "text": text, "size": len(data)})

    def write_text(self, path: str, text: str) -> ExecResult:
        p = Path(path)
        self.policy.assert_can_write(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return ExecResult(True, "write_text", "OK", {"path": str(p), "bytes": len(text.encode("utf-8"))})

    def append_text(self, path: str, text: str) -> ExecResult:
        p = Path(path)
        self.policy.assert_can_write(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(text)
        return ExecResult(True, "append_text", "OK", {"path": str(p), "bytes": len(text.encode("utf-8"))})

    def run_cmd(self, cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> ExecResult:
        if not self._is_cmd_allowed(cmd):
            return ExecResult(False, "run_cmd", "CMD_NOT_ALLOWED", {"cmd": cmd})

        run_cwd = Path(cwd).resolve() if cwd else None
        if run_cwd:
            self.policy.assert_can_read(run_cwd)

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            cp = subprocess.run(
                cmd,
                cwd=str(run_cwd) if run_cwd else None,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=self.policy.max_cmd_seconds,
            )
            ok = (cp.returncode == 0)
            return ExecResult(
                ok,
                "run_cmd",
                "OK" if ok else "NONZERO_EXIT",
                {"cmd": cmd, "returncode": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr},
            )
        except subprocess.TimeoutExpired:
            return ExecResult(False, "run_cmd", "TIMEOUT", {"cmd": cmd, "timeout_s": self.policy.max_cmd_seconds})
        except Exception as e:
            return ExecResult(False, "run_cmd", "ERROR", {"cmd": cmd, "error": str(e)})







