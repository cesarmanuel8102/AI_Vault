from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))

from brain_v9.core import session_memory_state as sms


class _PatchedPaths:
    def __init__(self, memory_path: Path, state_path: Path) -> None:
        self.memory_path = memory_path
        self.state_path = state_path
        self.old_memory_path = sms._cfg.MEMORY_PATH
        self.old_state_path = sms._cfg.STATE_PATH
        self.old_legacy_artifact = sms.SESSION_MEMORY_ARTIFACT

    def __enter__(self):
        sms._cfg.MEMORY_PATH = self.memory_path
        sms._cfg.STATE_PATH = self.state_path
        sms.SESSION_MEMORY_ARTIFACT = self.state_path / "session_memory.json"
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        sms._cfg.MEMORY_PATH = self.old_memory_path
        sms._cfg.STATE_PATH = self.old_state_path
        sms.SESSION_MEMORY_ARTIFACT = self.old_legacy_artifact


def _write_short_term(memory_root: Path, session_id: str, text: str) -> None:
    session_dir = memory_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "short_term.json").write_text(
        json.dumps({"count": 1, "messages": [{"role": "user", "content": text}]}),
        encoding="utf-8",
    )


def test_safe_session_id_preserves_normal_ids() -> None:
    assert sms._safe_session_id("default") == "default"
    assert sms._safe_session_id("cesar_main") == "cesar_main"
    assert sms._safe_session_id("sid-123") == "sid-123"


def test_safe_session_id_blocks_path_traversal() -> None:
    for raw in ["../evil", "..\\evil", "a/b", "a\\b", "", None]:
        safe = sms._safe_session_id(raw)  # type: ignore[arg-type]
        assert safe
        assert "/" not in safe
        assert "\\" not in safe
        assert ".." not in safe
        assert safe not in {".", ".."}


def test_artifact_path_is_namespaced() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with _PatchedPaths(root / "memory", root / "state"):
            alpha = sms._session_memory_artifact_path("alpha")
            beta = sms._session_memory_artifact_path("beta")
            assert alpha != beta
            assert alpha == root / "state" / "session_memory" / "alpha.json"
            assert beta == root / "state" / "session_memory" / "beta.json"


def test_build_session_memory_writes_separate_artifacts() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        memory_root = root / "memory"
        state_root = root / "state"
        _write_short_term(memory_root, "alpha", "alpha objective")
        _write_short_term(memory_root, "beta", "beta objective")

        with _PatchedPaths(memory_root, state_root):
            alpha_payload = sms.build_session_memory("alpha")
            beta_payload = sms.build_session_memory("beta")
            alpha_path = state_root / "session_memory" / "alpha.json"
            beta_path = state_root / "session_memory" / "beta.json"

            assert alpha_path.exists()
            assert beta_path.exists()
            assert not (state_root / "session_memory.json").exists()
            assert alpha_payload["session_id"] == "alpha"
            assert beta_payload["session_id"] == "beta"
            assert alpha_payload["objective"] != beta_payload["objective"]
            assert json.loads(alpha_path.read_text(encoding="utf-8"))["session_id"] == "alpha"
            assert json.loads(beta_path.read_text(encoding="utf-8"))["session_id"] == "beta"


def test_get_session_memory_latest_uses_matching_namespaced_cache() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state_root = root / "state"
        cache_dir = state_root / "session_memory"
        cache_dir.mkdir(parents=True)
        (cache_dir / "alpha.json").write_text(json.dumps({"session_id": "alpha", "objective": "a"}), encoding="utf-8")
        (cache_dir / "beta.json").write_text(json.dumps({"session_id": "beta", "objective": "b"}), encoding="utf-8")

        with _PatchedPaths(root / "memory", state_root):
            assert sms.get_session_memory_latest("alpha")["objective"] == "a"
            assert sms.get_session_memory_latest("beta")["objective"] == "b"


def test_legacy_global_artifact_fallback_when_matching_session() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state_root = root / "state"
        state_root.mkdir(parents=True)
        legacy = {"session_id": "legacy_sid", "objective": "legacy objective"}
        (state_root / "session_memory.json").write_text(json.dumps(legacy), encoding="utf-8")

        with _PatchedPaths(root / "memory", state_root):
            assert sms.get_session_memory_latest("legacy_sid")["objective"] == "legacy objective"
            other = sms.get_session_memory_latest("other")
            assert other["session_id"] == "other"
            assert other["objective"] != "legacy objective"


def test_no_real_memory_paths_used() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with _PatchedPaths(root / "memory", root / "state"):
            path = sms._session_memory_artifact_path("../evil")
            assert str(path).startswith(str(root / "state" / "session_memory"))
            assert ROOT not in path.parents


if __name__ == "__main__":
    tests = [
        test_safe_session_id_preserves_normal_ids,
        test_safe_session_id_blocks_path_traversal,
        test_artifact_path_is_namespaced,
        test_build_session_memory_writes_separate_artifacts,
        test_get_session_memory_latest_uses_matching_namespaced_cache,
        test_legacy_global_artifact_fallback_when_matching_session,
        test_no_real_memory_paths_used,
    ]
    for test in tests:
        test()
    print(f"OK: {len(tests)} session memory state tests passed")
