import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"tmp_agent"/"front_chat_ui_brain_provider_config_8091_01"

def test_01_doc_exists(): assert (ROOT/"docs"/"FRONT_CHAT_UI_BRAIN_PROVIDER_CONFIG_8091_01.md").exists()
def test_02_probe_passed(): assert json.loads((E/"container_provider_probe.json").read_text(encoding="utf-8-sig"))["container_to_brain_passed"] is True
def test_03_runbook_has_8091_url(): assert "http://host.docker.internal:8091/v1" in (ROOT/"docs"/"FRONT_CHAT_UI_BRAIN_PROVIDER_CONFIG_8091_01.md").read_text(encoding="utf-8")
