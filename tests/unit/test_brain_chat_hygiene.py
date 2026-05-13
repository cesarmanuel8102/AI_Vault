import json

import pytest


@pytest.mark.unit
def test_session_sanitizes_agent_footer_from_memory():
    from brain_v9.core.session import BrainSession

    text = "Resultado útil\n\n*[Agente ORAV (complex): 3 paso(s) -- completed]*"
    cleaned = BrainSession._sanitize_memory_content(text)

    assert cleaned == "Resultado útil"


@pytest.mark.unit
def test_temporal_query_detector():
    from brain_v9.core.session import BrainSession

    assert BrainSession._is_temporal_query("revisa el estado live de hoy") is True
    assert BrainSession._is_temporal_query("explica la arquitectura del brain") is False


@pytest.mark.unit
def test_session_sanitizes_raw_function_call_markup():
    from brain_v9.core.session import BrainSession

    raw = "<function_calls><invoke name=\"list_dir\"><parameter name=\"path\">C:/AI_VAULT</parameter></invoke></function_calls>"
    cleaned = BrainSession._sanitize_llm_chat_response(raw)

    assert "<function_calls" not in cleaned.lower()
    assert "<invoke name=" not in cleaned.lower()


@pytest.mark.unit
def test_render_agent_failure_reply_is_honest_and_hides_internal_markup():
    from brain_v9.core.session import BrainSession

    raw = "<function_calls><invoke name=\"list_dir\"></invoke></function_calls>"
    reply = BrainSession._render_agent_failure_reply("ghost_completion", raw)

    assert "no pude completar esta peticion con herramientas" in reply.lower()
    assert "no llego a ejecutar ninguna herramienta" in reply.lower()
    assert "<function_calls" not in reply.lower()
    assert "<invoke name=" not in reply.lower()


@pytest.mark.unit
def test_chat_interaction_review_query_detector():
    from brain_v9.core.session import BrainSession

    assert BrainSession._is_chat_interaction_review_query(
        "revisa las ultimas interacciones chat-brain y dime que esta fallando"
    ) is True
    assert BrainSession._is_chat_interaction_review_query(
        "explica la arquitectura general del brain"
    ) is False


@pytest.mark.unit
def test_llm_status_query_detector_and_fastpath():
    from brain_v9.core.session import BrainSession

    session = BrainSession("test_llm_status")
    assert BrainSession._is_llm_status_query("que llm estas usando como principal?") is True
    reply = session._maybe_fastpath("que llm estas usando como principal?", model_priority="chat")
    assert reply is not None
    text = reply["response"].lower()
    assert "primario para esta consulta" in text
    assert "kimi_cloud" in text
    assert "codex esta promovido para `code`" in text


@pytest.mark.unit
def test_codex_role_query_fastpath():
    from brain_v9.core.session import BrainSession

    session = BrainSession("test_codex_role")
    reply = session._maybe_fastpath(
        "que significa esa respuesta de estado del llm y por que no participa codex en chat general",
        model_priority="chat",
    )
    assert reply is not None
    text = reply["response"].lower()
    assert "rol actual de codex" in text
    assert "analysis_frontier" in text
    assert "chat general: no es principal" in text
    assert BrainSession._is_codex_role_query(
        "evalua tecnicamente la diferencia entre codex en code y codex en chat general dentro del brain"
    ) is False


@pytest.mark.unit
def test_codex_comparison_query_fastpath():
    from brain_v9.core.session import BrainSession

    session = BrainSession("test_codex_compare")
    assert BrainSession._is_codex_comparison_query(
        "evalua tecnicamente la diferencia entre codex en code y codex en chat general dentro del brain"
    ) is True
    reply = session._maybe_fastpath(
        "evalua tecnicamente la diferencia entre codex en code y codex en chat general dentro del brain",
        model_priority="chat",
    )
    assert reply is not None
    text = reply["response"].lower()
    assert "comparativa tecnica" in text
    assert "`code`" in text
    assert "`chat` general" in text


@pytest.mark.unit
def test_chat_dev_mode_persists_defaults(tmp_path, monkeypatch):
    import brain_v9.core.session as session_mod

    defaults_path = tmp_path / "chat_session_defaults.json"
    monkeypatch.setattr(session_mod, "_CHAT_SESSION_DEFAULTS_PATH", defaults_path)
    monkeypatch.setattr(session_mod, "BRAIN_CHAT_DEV_MODE", False)

    assert session_mod.BrainSession._load_chat_dev_mode_default() is False
    assert session_mod.BrainSession._persist_chat_dev_mode_default(True) is True
    assert session_mod.BrainSession._load_chat_dev_mode_default() is True


@pytest.mark.unit
def test_compact_chat_prompt_applies_to_short_general_query():
    from brain_v9.core.session import BrainSession

    assert BrainSession._should_use_compact_chat_prompt(
        "responde solo hola en una frase",
        "QUERY",
        [],
        "llama8b",
    ) is True

    assert BrainSession._should_use_compact_chat_prompt(
        "revisa C:\\AI_VAULT\\tmp_agent\\brain_v9\\core\\llm.py",
        "QUERY",
        [],
        "llama8b",
    ) is False


@pytest.mark.unit
def test_analysis_frontier_selector_for_non_operational_analysis():
    from brain_v9.core.session import BrainSession

    assert BrainSession._should_use_analysis_frontier(
        "que significa esa respuesta y por que codex no esta activo?",
        "CREATIVE",
        [],
        "chat",
    ) is True

    assert BrainSession._select_llm_chain(
        "que significa esa respuesta y por que codex no esta activo?",
        "CREATIVE",
        [],
        "chat",
    ) == "analysis_frontier"

    assert BrainSession._should_use_analysis_frontier(
        "revisa el estado de todos los servicios y ejecuta diagnostico",
        "ANALYSIS",
        [],
        "chat",
    ) is False


@pytest.mark.unit
def test_analysis_frontier_selector_for_brain_diagnostic_query():
    from brain_v9.core.session import BrainSession

    assert BrainSession._is_brain_diagnostic_analysis_query(
        "revisa la reciente promocion a principal de codex y porque no esta activo en chat"
    ) is True


@pytest.mark.unit
def test_code_change_request_uses_code_priority():
    from brain_v9.core.session import BrainSession

    session = BrainSession("test_code_priority")
    assert session._is_code_change_request("modifica el color de fondo del chat a uno mas claro") is True
    assert session._select_agent_model_priority(
        "modifica el color de fondo del chat a uno mas claro",
        "chat",
    ) == "code"
    assert session._select_agent_model_priority(
        "revisa el estado del brain",
        "chat",
    ) == "chat"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grounded_ui_edit_fastpath_updates_bg(monkeypatch, tmp_path):
    import brain_v9.core.session as session_mod

    ui_file = tmp_path / "index.html"
    ui_file.write_text(":root { --bg: #0f1117; --surface: #1a1d27; }", encoding="utf-8")
    monkeypatch.setattr(session_mod, "_UI_INDEX", ui_file)
    monkeypatch.setattr(session_mod, "_UI_EDIT_STATE_PATH", tmp_path / "ui_edit_state.json")

    session = session_mod.BrainSession("test_ui_edit_fastpath")
    result = await session._maybe_grounded_ui_edit_fastpath(
        "modifica el color de fondo del chat a uno mas claro y dime exactamente que archivo tocaste"
    )

    assert result is not None
    assert result["success"] is True
    text = result["response"].lower()
    assert "archivo_tocado" in text
    assert str(ui_file).lower() in text
    assert "#d9dee8" in ui_file.read_text(encoding="utf-8").lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grounded_ui_edit_fastpath_restores_previous_dark_color(monkeypatch, tmp_path):
    import brain_v9.core.session as session_mod

    ui_file = tmp_path / "index.html"
    ui_file.write_text(":root { --bg: #eef2f8; --surface: #1a1d27; }", encoding="utf-8")
    state_file = tmp_path / "ui_edit_state.json"
    state_file.write_text(
        json.dumps({"bg": {"last_old_color": "#171c26", "last_new_color": "#eef2f8", "default_dark_color": "#0f1117"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_mod, "_UI_INDEX", ui_file)
    monkeypatch.setattr(session_mod, "_UI_EDIT_STATE_PATH", state_file)

    session = session_mod.BrainSession("test_ui_restore_fastpath")
    result = await session._maybe_grounded_ui_edit_fastpath(
        "vuelve a dejar el fondo del chat oscuro"
    )

    assert result is not None
    assert result["success"] is True
    assert "#0f1117" in ui_file.read_text(encoding="utf-8").lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grounded_ui_edit_fastpath_restores_previous_color_from_shorthand(monkeypatch, tmp_path):
    import brain_v9.core.session as session_mod

    ui_file = tmp_path / "index.html"
    ui_file.write_text(":root { --bg: #eef2f8; --surface: #1a1d27; }", encoding="utf-8")
    state_file = tmp_path / "ui_edit_state.json"
    state_file.write_text(
        json.dumps({"bg": {"last_old_color": "#0f1117", "last_new_color": "#eef2f8", "default_dark_color": "#0f1117"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_mod, "_UI_INDEX", ui_file)
    monkeypatch.setattr(session_mod, "_UI_EDIT_STATE_PATH", state_file)

    session = session_mod.BrainSession("test_ui_restore_shorthand")
    result = await session._maybe_grounded_ui_edit_fastpath(
        "retornalo al color anterior"
    )

    assert result is not None
    assert result["success"] is True
    assert "#0f1117" in ui_file.read_text(encoding="utf-8").lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grounded_ui_edit_fastpath_prioritizes_explicit_dark_over_previous(monkeypatch, tmp_path):
    import brain_v9.core.session as session_mod

    ui_file = tmp_path / "index.html"
    ui_file.write_text(":root { --bg: #0f1117; --surface: #1a1d27; }", encoding="utf-8")
    state_file = tmp_path / "ui_edit_state.json"
    state_file.write_text(
        json.dumps({"bg": {"last_old_color": "#eef2f8", "last_new_color": "#0f1117", "default_dark_color": "#0f1117"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_mod, "_UI_INDEX", ui_file)
    monkeypatch.setattr(session_mod, "_UI_EDIT_STATE_PATH", state_file)

    session = session_mod.BrainSession("test_ui_restore_precedence")
    result = await session._maybe_grounded_ui_edit_fastpath(
        "deja el chat como estaba antes, oscuro"
    )

    assert result is not None
    assert result["success"] is True
    assert "#0f1117" in ui_file.read_text(encoding="utf-8").lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_grounded_ui_edit_fastpath_moves_send_button(monkeypatch, tmp_path):
    import brain_v9.core.session as session_mod

    ui_file = tmp_path / "index.html"
    ui_file.write_text("  /* ── Status / Metrics ── */\n", encoding="utf-8")
    monkeypatch.setattr(session_mod, "_UI_INDEX", ui_file)

    session = session_mod.BrainSession("test_ui_move_fastpath")
    result = await session._maybe_grounded_ui_edit_fastpath(
        "mueve el boton de enviar 20px a la izquierda en el chat y dime que archivo tocaste"
    )

    assert result is not None
    assert result["success"] is True
    text = result["response"].lower()
    assert "selector_css: #send-btn" in text
    assert "translatex(-20px)" in ui_file.read_text(encoding="utf-8").lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_confirmation_resumes_pending_continuation(monkeypatch):
    from brain_v9.core.session import BrainSession

    session = BrainSession("test_pending_resume")
    session._set_pending_continuation(
        "modifica el color de fondo del chat a uno mas claro",
        model_priority="code",
        source="agent",
    )

    calls = []

    async def fake_chat(message, model_priority="chat"):
        calls.append((message, model_priority))
        return {
            "success": True,
            "content": "hecho",
            "response": "hecho",
            "route": "agent",
            "intent": "CODE",
        }

    monkeypatch.setattr(session, "chat", fake_chat)

    result = await session._maybe_resume_pending_continuation("si, confirmado")

    assert result["success"] is True
    assert calls == [("modifica el color de fondo del chat a uno mas claro", "code")]
    assert session._pending_continuation is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_confirmation_without_pending_returns_fastpath_ack(monkeypatch):
    from brain_v9.core.session import BrainSession
    import brain_v9.governance.execution_gate as gate_mod

    class _NoPendingGate:
        def get_pending(self, session_id=None):
            return []

    monkeypatch.setattr(gate_mod, "get_gate", lambda: _NoPendingGate())

    session = BrainSession("test_confirmation_noop")
    result = await session.chat("si, confirmado", model_priority="chat")

    assert result["success"] is True
    assert result["route"] == "confirmation_noop"
    assert "no hay una accion pendiente" in result["response"].lower()


@pytest.mark.unit
def test_qc_live_query_detector():
    from brain_v9.core.session import BrainSession

    assert BrainSession._is_qc_live_query("conectate al QC live y dime que ves hoy") is True
    assert BrainSession._is_qc_live_query("explica quantconnect research") is False


@pytest.mark.unit
def test_benign_security_audit_uses_analysis_frontier():
    from brain_v9.core.session import BrainSession

    message = "haz una auditoria de seguridad benigna del Brain local y dime superficies obvias de exposicion, sin explotar nada"
    assert BrainSession._is_benign_security_audit_query(message) is True
    assert BrainSession._should_use_analysis_frontier(
        message,
        "COMMAND",
        [],
        "chat",
    ) is True


@pytest.mark.unit
def test_execution_gate_expires_stale_pending(monkeypatch, tmp_path):
    import json
    from datetime import datetime, timedelta

    import brain_v9.governance.execution_gate as gate_mod

    state_path = tmp_path / "execution_gate_state.json"
    old_ts = (datetime.now() - timedelta(hours=72)).isoformat()
    state_path.write_text(json.dumps({
        "mode": "build",
        "pending": [
            {
                "id": "confirm_old",
                "tool": "auto_promote_strategies",
                "args": {},
                "risk": "P2",
                "reason": "stale",
                "created_at": old_ts,
                "status": "awaiting_confirmation",
            }
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(gate_mod, "_STATE_PATH", state_path)

    gate = gate_mod.ExecutionGate()

    assert gate.get_pending() == []
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["pending"][0]["status"] == "expired"


@pytest.mark.unit
def test_execution_gate_filters_pending_by_session(monkeypatch, tmp_path):
    import json

    import brain_v9.governance.execution_gate as gate_mod

    state_path = tmp_path / "execution_gate_state.json"
    state_path.write_text(json.dumps({
        "mode": "build",
        "pending": [
            {
                "id": "confirm_a",
                "tool": "auto_promote_strategies",
                "args": {},
                "session_id": "sess_a",
                "risk": "P2",
                "reason": "x",
                "created_at": "2026-05-07T10:00:00",
                "status": "awaiting_confirmation",
            },
            {
                "id": "confirm_b",
                "tool": "auto_promote_strategies",
                "args": {},
                "session_id": "sess_b",
                "risk": "P2",
                "reason": "x",
                "created_at": "2026-05-07T10:01:00",
                "status": "awaiting_confirmation",
            },
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(gate_mod, "_STATE_PATH", state_path)

    gate = gate_mod.ExecutionGate()

    assert [p["id"] for p in gate.get_pending("sess_a")] == ["confirm_a"]
    approved = gate.approve_latest("sess_b")
    assert approved["id"] == "confirm_b"
    assert gate.get_pending("sess_c") == []


@pytest.mark.unit
def test_chat_interaction_review_fastpath_returns_grounded_findings(monkeypatch):
    import brain_v9.core.session as session_mod

    session = session_mod.BrainSession.__new__(session_mod.BrainSession)

    def fake_read_json(path, default=None):
        path_s = str(path)
        if path_s.endswith("chat_metrics_latest.json"):
            return {
                "ghost_completion_count": 2,
                "canned_no_result_count": 3,
                "avg_latency_ms": 27881.3,
            }
        if path_s.endswith("episodic_memory.json"):
            return [
                {
                    "type": "task_result",
                    "timestamp": "2026-05-06T18:25:20.620537",
                    "content": "Tarea: revisa el estado de todos los servicios del ecosistema AI_VAULT | Resultado: fallo | Tools:  | 0 OK, 0 fail | 1 pasos",
                }
            ]
        if path_s.endswith("status_latest.json"):
            return {
                "recent_incidents": [
                    {
                        "requested_tool": "scan_local_network",
                        "reason": "Expected 4 octets in 'auto'",
                    }
                ]
            }
        return default

    monkeypatch.setattr(session_mod, "read_json", fake_read_json)

    reply = session._chat_interaction_review_fastpath()
    text = reply["response"].lower()

    assert reply["success"] is True
    assert "ghost_completion=2" in text
    assert "canned_no_result=3" in text
    assert "hubo fallos reales de scan_local_network" in text
    assert "el bug de 'auto' ya fue corregido" in text
    assert "endurecer la ruta que hoy cae a 'resumen extractivo'" in text


@pytest.mark.unit
def test_episodic_memory_can_filter_old_entries(tmp_path):
    import json
    from datetime import datetime, timedelta

    from brain_v9.core.knowledge import EpisodicMemory

    path = tmp_path / "episodic.json"
    old_ts = (datetime.now() - timedelta(hours=200)).isoformat()
    new_ts = (datetime.now() - timedelta(hours=2)).isoformat()
    payload = [
        {"id": 1, "type": "task_result", "content": "estado live antiguo", "keywords": ["estado", "live"], "timestamp": old_ts},
        {"id": 2, "type": "task_result", "content": "estado live reciente", "keywords": ["estado", "live"], "timestamp": new_ts},
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    memory = EpisodicMemory(path=path)
    results = memory.recall("estado live", max_results=5, max_age_hours=72)

    assert len(results) == 1
    assert results[0]["content"] == "estado live reciente"


@pytest.mark.unit
def test_episodic_memory_compact_repairs_duplicate_ids_and_old_entries(tmp_path):
    import json
    from datetime import datetime, timedelta

    from brain_v9.core.knowledge import EpisodicMemory

    path = tmp_path / "episodic.json"
    old_ts = (datetime.now() - timedelta(days=400)).isoformat()
    new_ts = (datetime.now() - timedelta(hours=3)).isoformat()
    payload = [
        {"id": 501, "type": "task_result", "content": "estado repetido", "keywords": ["estado"], "timestamp": old_ts},
        {"id": 501, "type": "task_result", "content": "estado repetido", "keywords": ["estado"], "timestamp": new_ts},
        {"id": 777, "type": "fact", "content": "contexto reciente", "keywords": ["contexto"], "timestamp": new_ts},
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    memory = EpisodicMemory(path=path)
    report = memory.compact(max_age_hours=24 * 30, keep_recent=2, dry_run=False)

    repaired = json.loads(path.read_text(encoding="utf-8"))
    assert report["removed_total"] == 1
    assert report["after"]["duplicate_exact_count"] == 0
    assert [entry["id"] for entry in repaired] == [1, 2]
    assert repaired[0]["content"] == "estado repetido"
    assert repaired[1]["content"] == "contexto reciente"


@pytest.mark.unit
def test_semantic_memory_compact_removes_duplicate_records(tmp_path):
    from datetime import datetime, timedelta, timezone

    from brain_v9.core.semantic_memory import SemanticMemory

    root = tmp_path / "semantic"
    memory = SemanticMemory(root=root)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat().replace("+00:00", "Z")
    new_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    memory.records_path.parent.mkdir(parents=True, exist_ok=True)
    memory.records_path.write_text(
        "\n".join(
            [
                '{"id":"a1","created_utc":"%s","source":"chat","session_id":"default","kind":"note","text":"hallazgo duplicado","metadata":{}}' % old_ts,
                '{"id":"a2","created_utc":"%s","source":"chat","session_id":"default","kind":"note","text":"hallazgo duplicado","metadata":{}}' % new_ts,
                '{"id":"b1","created_utc":"%s","source":"chat","session_id":"default","kind":"note","text":"hallazgo reciente","metadata":{}}' % new_ts,
            ]
        ),
        encoding="utf-8",
    )

    report = memory.compact(max_age_hours=24 * 30, keep_recent=2, dry_run=False)
    records = memory._read_records()

    assert report["removed_total"] == 1
    assert report["after"]["duplicate_exact_count"] == 0
    assert len(records) == 2
    assert any(record["text"] == "hallazgo reciente" for record in records)
    assert memory.index_path.exists()


@pytest.mark.unit
def test_semantic_memory_faiss_compact_supports_temporal_hygiene(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS

    root = tmp_path / "semantic_faiss"
    memory = SemanticMemoryFAISS(root=root)
    monkeypatch.setattr(memory, "rebuild_index", lambda show_progress=False: {"ok": True, "records": 2})
    old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat().replace("+00:00", "Z")
    new_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    memory.records_path.parent.mkdir(parents=True, exist_ok=True)
    memory.records_path.write_text(
        "\n".join(
            [
                '{"id":"a1","created_utc":"%s","source":"chat","session_id":"default","kind":"note","text":"hallazgo duplicado","metadata":{}}' % old_ts,
                '{"id":"a2","created_utc":"%s","source":"chat","session_id":"default","kind":"note","text":"hallazgo duplicado","metadata":{}}' % new_ts,
                '{"id":"b1","created_utc":"%s","source":"chat","session_id":"default","kind":"note","text":"hallazgo reciente","metadata":{}}' % new_ts,
            ]
        ),
        encoding="utf-8",
    )

    report = memory.compact(max_age_hours=24 * 30, keep_recent=2, dry_run=False)
    records = memory._read_records()
    hits = memory.format_hits_for_prompt([
        {"score": 0.9, "source": "chat", "kind": "note", "age_hours": 2.0, "snippet": "resultado"}
    ])

    assert report["removed_total"] == 1
    assert report["after"]["duplicate_exact_count"] == 0
    assert len(records) == 2
    assert "HISTORICA" in hits
    assert "age_h=2.0" in hits


@pytest.mark.unit
def test_chat_endpoint_returns_clean_user_response(api_client, monkeypatch):
    import brain_v9.core.session as session_mod

    class DummySession:
        async def chat(self, message: str, model_priority: str):
            return {
                "success": True,
                "content": "Resultado útil",
                "model": "agent_orav",
            }

    monkeypatch.setattr(session_mod, "get_or_create_session", lambda session_id, sessions: DummySession())

    response = api_client.post("/chat", json={"message": "revisa estado live de hoy", "session_id": "test", "model_priority": "ollama"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Resultado útil"
    assert "Agente ORAV" not in payload["response"]
    assert "[DEV]" not in payload["response"]
