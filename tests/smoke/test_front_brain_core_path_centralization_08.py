"""Smoke test: active core paths derive from brain_v9.config.BASE_PATH."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_governed_action_kernel_paths_are_base_path_relative():
    import brain_v9.core.governed_action_kernel as gak
    from brain_v9.config import BASE_PATH

    source = Path(gak.__file__).read_text(encoding="utf-8")
    assert 'C:/AI_VAULT' not in source
    assert 'C:\\AI_VAULT' not in source
    assert gak._WORKSPACE_ROOT == (BASE_PATH / "tmp_agent" / "workspace").resolve()
    assert gak._is_within_workspace(str(BASE_PATH / "tmp_agent" / "workspace" / "safe.txt")) is True
    assert gak._is_within_workspace(str(BASE_PATH / "tmp_agent" / "not_workspace" / "x.txt")) is False
    assert gak._is_protected_path("memory/semantic/semantic_memory.jsonl") is True


def test_semantic_memory_faiss_detection_uses_semantic_root():
    import brain_v9.core.semantic_memory as sm

    source = inspect.getsource(sm.get_semantic_memory)
    module_source = Path(sm.__file__).read_text(encoding="utf-8")
    assert 'C:/AI_VAULT' not in module_source
    assert 'C:\\AI_VAULT' not in module_source
    assert 'SEMANTIC_ROOT / "semantic_memory_faiss.index"' in source
