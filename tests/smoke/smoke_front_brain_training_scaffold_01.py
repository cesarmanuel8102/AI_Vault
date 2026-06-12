import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))

from brain_v9.training import LessonCard, MistakeEntry, MistakeRegistry, PromotionGate, TeacherStudentLoop


def test_01_lesson_card_validates_and_serializes():
    card = LessonCard(
        lesson_id="lesson_test",
        domain="runtime_quality",
        mistake_observed="fallback counted as success",
        correct_behavior="classify fallback explicitly",
        example_prompt="explain autonomy",
        bad_response_summary="timeout text",
        good_response_target="structured fallback metadata",
        test_to_prevent_regression="test_name",
    )
    assert card.to_dict()["promotion_status"] == "candidate"


def test_02_mistake_registry_rejects_duplicates():
    entry = MistakeEntry("m1", "runtime", "medium", "rule", 1, "lesson_test", "test_name")
    registry = MistakeRegistry()
    registry.add(entry)
    assert registry.find("m1") == entry
    try:
        registry.add(entry)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate mistake accepted")


def test_03_promotion_gate_pass_fail():
    assert PromotionGate("g1", "score", 0.5, 0.7, 0.8).pass_fail == "pass"
    assert PromotionGate("g2", "score", 0.5, 0.7, 0.6).pass_fail == "fail"
    assert PromotionGate("g3", "score", 0.5, 0.7).pass_fail == "not_measured"


def test_04_teacher_student_loop_outputs_structured_cycle():
    cycle = TeacherStudentLoop().run_cycle(
        "cycle_test",
        "Brain proposed fallback classification and observer reports.",
        timeout_fallback_count=1,
        raw_cot_count=0,
        protected_mutation=False,
    )
    payload = cycle.to_dict()
    assert payload["lessons"]
    assert payload["mistakes"]
    assert payload["promotion_gates"]
    assert payload["promotion_gates"][0]["metric_name"] == "timeout_fallback_count"


def test_05_no_protected_paths_staged():
    import subprocess
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
