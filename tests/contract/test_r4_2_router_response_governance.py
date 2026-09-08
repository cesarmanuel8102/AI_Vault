"""Contract for the R4.2 internal response-governance extraction."""

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_response_governance_is_an_internal_effect_free_module():
    from brain_v9.core import router_response_governance as governance

    module_path = ROOT / "tmp_agent" / "brain_v9" / "core" / "router_response_governance.py"
    assert module_path.exists()
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not imported_roots.intersection(
        {"asyncio", "subprocess", "socket", "requests", "httpx", "urllib", "pathlib", "os"}
    )
    assert governance._strip_raw_cot_fields(
        {"raw_chain_of_thought": "hidden", "nested": {"private_reasoning": "hidden", "safe": 1}}
    ) == {"nested": {"safe": 1}}


def test_router_reexports_the_extracted_governance_boundary():
    from brain_v9.core import router_response_governance as governance
    from brain_v9.core import router_entrypoint

    assert router_entrypoint.apply_governance is governance.apply_governance
    governed = router_entrypoint.apply_governance(
        "analysis: hidden reasoning raw_chain_of_thought",
        {"private_reasoning": "do not expose", "safe": True},
    )
    assert governed["no_cot_leak"] is True
    assert "raw_chain_of_thought" not in governed["content"]
    assert governed["metadata"] == {"safe": True, "thinking_stripped": governed["metadata"]["thinking_stripped"]}
