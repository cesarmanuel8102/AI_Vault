from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "tmp_agent/brain_v9/ui/index.html"


def test_ui_blocks_chat_before_strict_operator_request_without_token():
    html = UI.read_text(encoding="utf-8")

    assert "function requireOperatorTokenForChat()" in html
    assert "if (!requireOperatorTokenForChat()) return;" in html
    assert "Token de operador requerido. Pega el token que imprimió el launcher local" in html
    assert "showTokenBanner(true);" in html


def test_ui_does_not_commit_local_operator_token_value():
    html = UI.read_text(encoding="utf-8")

    assert "AGENTV2_TEST_ADMIN_TOKEN_08F8_R1B" not in html
    assert "X-Brain-Token" in html
    assert "localStorage.setItem(_TOKEN_KEY, token)" in html
