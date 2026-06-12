from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md"


def test_01_openwebui_runbook_exists_and_contains_provider_details():
    text = DOC.read_text(encoding="utf-8")
    assert "http://host.docker.internal:8091/v1" in text
    assert "brain-v9-local" in text
    assert "dummy/local" in text


def test_02_openwebui_runbook_contains_validation_and_rollback():
    text = DOC.read_text(encoding="utf-8").lower()
    assert "/v1/models" in text
    assert "/v1/chat/completions" in text
    assert "rollback" in text
    assert "8090" in text
