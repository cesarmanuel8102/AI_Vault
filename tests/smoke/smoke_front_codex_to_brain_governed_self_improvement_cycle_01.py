import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_codex_to_brain_governed_self_improvement_cycle_01"
DOC = ROOT / "docs" / "FRONT_CODEX_TO_BRAIN_GOVERNED_SELF_IMPROVEMENT_CYCLE_01.md"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_doc_exists():
    assert DOC.exists()


def test_02_dialogue_results_exists():
    assert (EVIDENCE / "dialogue_results.json").exists()


def test_03_evaluation_scorecard_exists():
    assert (EVIDENCE / "evaluation_scorecard.json").exists()


def test_04_cesar_review_report_exists():
    assert (EVIDENCE / "cesar_review_report.md").exists()


def test_05_at_least_24_prompts_attempted():
    assert _json(EVIDENCE / "dialogue_results.json")["prompts_attempted"] >= 24


def test_06_average_score_exists():
    score = _json(EVIDENCE / "evaluation_scorecard.json")
    assert isinstance(score["average_score"], (int, float))


def test_07_no_memory_semantic_staged():
    assert "memory/semantic" not in _git(["diff", "--cached", "--name-only"]).replace("\\", "/")


def test_08_no_trading_staged():
    assert "trading/" not in _git(["diff", "--cached", "--name-only"]).replace("\\", "/")


def test_09_no_b8_staged():
    assert "B8/" not in _git(["diff", "--cached", "--name-only"]).replace("\\", "/")


def test_10_no_tmp_agent_strategies_staged():
    assert "tmp_agent/strategies" not in _git(["diff", "--cached", "--name-only"]).replace("\\", "/")


def test_11_roadmap_status_json_valid():
    assert isinstance(_json(ROOT / "ROADMAP_STATUS.json"), dict)


def test_12_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
