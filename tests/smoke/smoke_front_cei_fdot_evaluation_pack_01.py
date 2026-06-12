import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "tests" / "fixtures" / "cei_fdot_eval_pack_v1.json"
ROADMAP = ROOT / "ROADMAP_STATUS.json"
LEDGER = ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md"


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_cei_fdot_pack_shape_and_size():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    assert data["pack_id"] == "cei_fdot_eval_pack_v1"
    assert data["mode"] == "behavioral_evaluation_only"
    assert len(data["prompts"]) >= 12
    required = {"id", "category", "prompt", "must_include", "must_not_include"}
    ids = set()
    for item in data["prompts"]:
        assert required <= set(item)
        assert item["id"] not in ids
        ids.add(item["id"])
        assert item["must_include"]
        assert item["must_not_include"]


def test_02_pack_does_not_claim_official_fdot_fact_database():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    assert data["source_policy"]["internet_required"] is False
    assert data["source_policy"]["official_spec_facts_embedded"] is False
    assert data["source_policy"]["must_not_fabricate_fdot_sections"] is True
    text = PACK.read_text(encoding="utf-8").lower()
    assert "behavioral_evaluation_only" in text
    assert "not an fdot specification database" in text


def test_03_pack_requires_evidence_uncertainty_context_and_contract_docs():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    flags = set(data["expected_behavior_flags"])
    assert "asks_for_evidence" in flags
    assert "states_uncertainty" in flags
    assert "requests_spec_year_or_project_context" in flags
    assert "distinguishes_field_guidance_from_official_spec" in flags
    assert "refuses_to_invent_citations" in flags
    assert "recommends_checking_contract_documents" in flags


def test_04_required_system_files_still_valid():
    json.loads(ROADMAP.read_text(encoding="utf-8"))
    assert LEDGER.exists()


def test_05_no_protected_paths_staged():
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
