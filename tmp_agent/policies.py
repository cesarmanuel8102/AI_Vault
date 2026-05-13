# policies.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class SandboxPolicy:
    """
    Políticas duras del Dev Sandbox.
    - No tocar 00_identity.
    - Solo escribir dentro de tmp_agent/workspace o tmp_agent/runs o tmp_agent/proposals o tmp_agent/state o tmp_agent/logs.
    - Lectura permitida (opt-in) sobre workspace\\brainlab y state/logs para análisis y diffs.
    """

    tmp_root: Path
    allow_read_roots: List[Path]
    allow_write_roots: List[Path]
    deny_roots: List[Path]
    max_cmd_seconds: int = 60
    max_iters: int = 20

    @staticmethod
    def default() -> "SandboxPolicy":
        tmp_root = Path(r"C:\AI_VAULT\tmp_agent").resolve()

        allow_write = [
            (tmp_root / "workspace").resolve(),
            (tmp_root / "runs").resolve(),
            (tmp_root / "proposals").resolve(),
            (tmp_root / "state").resolve(),
            (tmp_root / "logs").resolve(),
        ]

        allow_read = [
            tmp_root,
            Path(r"C:\AI_VAULT\workspace\brainlab").resolve(),
            Path(r"C:\AI_VAULT\state").resolve(),
            Path(r"C:\AI_VAULT\logs").resolve(),
        ]

        deny = [
            Path(r"C:\AI_VAULT\00_identity").resolve(),  # runtime productivo (prohibido)
        ]

        return SandboxPolicy(
            tmp_root=tmp_root,
            allow_read_roots=allow_read,
            allow_write_roots=allow_write,
            deny_roots=deny,
            max_cmd_seconds=60,
            max_iters=20,
        )

    def _is_under_any_root(self, path: Path, roots: Iterable[Path]) -> bool:
        p = path.resolve()
        for r in roots:
            r = r.resolve()
            try:
                p.relative_to(r)
                return True
            except Exception:
                continue
        return False

    def assert_can_read(self, path: Path) -> None:
        p = path.resolve()
        if self._is_under_any_root(p, self.deny_roots):
            raise PermissionError(f"READ_DENIED_BY_POLICY: {p}")
        if not self._is_under_any_root(p, self.allow_read_roots):
            raise PermissionError(f"READ_NOT_IN_ALLOWLIST: {p}")

    def assert_can_write(self, path: Path) -> None:
        p = path.resolve()
        if self._is_under_any_root(p, self.deny_roots):
            raise PermissionError(f"WRITE_DENIED_BY_POLICY: {p}")
        if not self._is_under_any_root(p, self.allow_write_roots):
            raise PermissionError(f"WRITE_NOT_IN_ALLOWLIST: {p}")

