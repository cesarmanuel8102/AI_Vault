from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_prompt_profiles_cover_required_styles():
    from tmp_agent.brain_v9.autonomy.dialogue_prompt_profiles import PROMPT_PROFILES

    profile_ids = {p.profile_id for p in PROMPT_PROFILES}
    assert len(PROMPT_PROFILES) >= 8
    for expected in {"exact_output", "bullet_only", "json_only", "role_compressed", "one_sentence_proposal", "critic", "revise", "score"}:
        assert expected in profile_ids


def test_provider_calibrator_uses_provider_probe_readonly_contract():
    source = read("tmp_agent/brain_v9/autonomy/provider_dialogue_calibrator.py")
    assert '"provider_probe": True' in source
    assert '"read_only": True' in source
    assert '"evaluation": True' in source
    assert "provider_selected" in source
    assert "model_selected" in source
    assert "fallback_used" in source
    assert "content_non_empty" in source


def test_calibration_summary_classifies_partial_micro_prompt_mode():
    from tmp_agent.brain_v9.autonomy.provider_dialogue_calibrator import DialogueCalibrationResult, summarize_calibration

    results = [
        DialogueCalibrationResult("exact_output", "kimi_k2_6_cloud", "kimi-k2.6:cloud", "FAST_SUCCESS", False, True, True, 10),
        DialogueCalibrationResult("bullet_only", "codex", "gpt-5.5", "FAST_SUCCESS", True, True, True, 10),
    ]
    summary = summarize_calibration(results)
    assert summary.kimi_open_dialogue_stability == "KIMI_OPEN_AUTONOMY_DIALOGUE_PARTIAL_MICRO_PROMPTS_ONLY"
    assert summary.recommended_mode == "codex_mentor_with_kimi_micro_prompts"


def test_calibrator_has_no_writes_to_protected_paths():
    source = read("tmp_agent/brain_v9/autonomy/provider_dialogue_calibrator.py")
    forbidden = ["memory/semantic", "semantic_memory_faiss", "tmp_agent/strategies", "trading/", "B8/", ".env"]
    for token in forbidden:
        assert token not in source
