import json


def test_build_session_memory_creates_canonical_artifact(isolated_base_path, monkeypatch):
    import brain_v9.core.session_memory_state as sms

    base = isolated_base_path
    memory_dir = base / "tmp_agent" / "memory" / "sess1"
    state_dir = base / "tmp_agent" / "state"
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "security").mkdir(parents=True, exist_ok=True)

    (memory_dir / "short_term.json").write_text(
        json.dumps(
            {
                "count": 4,
                "messages": [
                    {"role": "user", "content": "revisa C:\\AI_VAULT\\tmp_agent\\brain_v9\\main.py"},
                    {"role": "assistant", "content": "vi el archivo y el foco sigue en edge"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (memory_dir / "long_term.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-03-27T12:00:00Z",
                    "summary": "Se decidió priorizar edge validation antes que optimización.",
                    "source": "llm",
                }
            ]
        ),
        encoding="utf-8",
    )
    (state_dir / "utility_u_latest.json").write_text(
        json.dumps({"blockers": ["sample_not_ready"]}),
        encoding="utf-8",
    )
    (state_dir / "meta_governance_status_latest.json").write_text(
        json.dumps(
            {
                "top_action": "increase_resolved_sample",
                "control_layer_mode": "ACTIVE",
                "current_focus": {"action": "increase_resolved_sample"},
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "security" / "security_posture_latest.json").write_text(
        json.dumps({"secrets_triage": {"current_actionable_candidate_count": 2}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(sms._cfg, "MEMORY_PATH", base / "tmp_agent" / "memory")
    monkeypatch.setattr(sms._cfg, "STATE_PATH", state_dir)
    monkeypatch.setattr(sms, "SESSION_MEMORY_ARTIFACT", state_dir / "session_memory.json")

    payload = sms.build_session_memory("sess1")

    assert payload["session_id"] == "sess1"
    assert payload["objective"].startswith("revisa")
    assert payload["important_vars"]["top_action"] == "increase_resolved_sample"
    assert "sample_not_ready" in payload["open_risks"]
    assert "security_review_required_count=2" in payload["open_risks"]
    assert any(path.endswith("main.py") for path in payload["key_files"])
    assert (state_dir / "session_memory.json").exists()
