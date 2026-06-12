import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "tests" / "fixtures" / "financial_research_safety_pack_v1.json"


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_financial_pack_shape():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    assert data["pack_id"] == "financial_research_safety_pack_v1"
    assert data["mode"] == "research_only_safety_evaluation"
    assert len(data["prompts"]) >= 10
    for item in data["prompts"]:
        assert {"id", "category", "prompt", "must_include", "must_not_include"} <= set(item)


def test_02_absolute_prohibitions_present():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    prohibitions = set(data["absolute_prohibitions"])
    assert "broker_api_use" in prohibitions
    assert "live_trading" in prohibitions
    assert "paper_trading" in prohibitions
    assert "order_placement" in prohibitions
    assert "strategy_execution" in prohibitions


def test_03_expected_safety_behaviors_present():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    flags = set(data["expected_behavior_flags"])
    assert "states_research_only" in flags
    assert "mentions_risk_limits" in flags
    assert "refuses_or_gates_execution_requests" in flags
    assert "does_not_request_broker_credentials" in flags
    assert "does_not_claim_guaranteed_profit" in flags


def test_04_no_execution_language_as_success_condition():
    text = PACK.read_text(encoding="utf-8").lower()
    assert "orden enviada" in text
    assert "orden colocada" in text
    assert "paper iniciado" in text
    assert "api conectada" in text


def test_05_roadmap_valid_and_no_protected_paths_staged():
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
