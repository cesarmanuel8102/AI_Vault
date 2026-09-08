from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "tests" / "smoke" / "smoke_front_chat_router_preservation_entrypoint_01.py"


def test_chat_router_smoke_uses_its_checkout_and_route_module():
    source = SMOKE.read_text(encoding="utf-8")

    assert '"C:\\\\AI_VAULT_CANONICAL"' not in source
    assert "ROUTES = ROOT / \"tmp_agent\" / \"brain_v9\" / \"routes\" / \"chat_entrypoint_routes.py\"" in source
    assert "def _require_memory_artifacts()" in source
    assert source.count("\n    _require_memory_artifacts()") == 4
    assert "BASE_PATH.resolve() == ROOT.resolve()" in source
    assert "assert \"handle_chat_entrypoint(\" in chat_block" in source
