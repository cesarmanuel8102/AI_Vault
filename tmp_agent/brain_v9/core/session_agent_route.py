"""Agent route helper for the chat session.

B7-STRANGLER-10B: mechanically extracted _route_to_agent.
This module must not import the session module or instantiate the chat session.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict

async def _route_to_agent(session, message: str, model_priority: str) -> Dict:
    # TOOL-01: try deterministic router first
    router_result = await session._tool01_router(message)
    if router_result is not None:
        ok = router_result.get("success", False)
        blocked = router_result.get("blocked_by_policy", False)
        notice = "Tool ejecutada realmente." if ok else ("Tool bloqueada por política." if blocked else "Tool falló.")
        payload = {
            "success": ok,
            "content": f"{notice}\n\n{json.dumps(router_result, indent=2, ensure_ascii=False)}",
            "response": notice,
            "route": "tool01_router",
            "tool01_router_used": True,
            "tool01_real": True,
            "tools_executed_count": 1,
            "tool_name": router_result.get("tool_name"),
            "blocked_by_policy": blocked,
            "fallback": False,
            "model": "tool01_router",
            "model_used": "tool01_router",
            "agent_steps": 1,
            "agent_status": "tool01_real" if ok else "tool01_blocked" if blocked else "tool01_failed",
            "tools_executed": 1,
            "tool_names": [router_result.get("tool_name")],
            "tool_result": router_result,
        }
        return payload
    
    msg = message.lower()
    # Dashboard fastpath inside agent route
    if session._is_dashboard_query(msg):
        # PHASE E.2: Epistemic check - block dashboard fastpath when user asks
        # about capability to verify without tools/http first
        msg_lower = message.lower()
        is_epistemic_question = (
            (("primero dime" in msg_lower or "puedes afirmar" in msg_lower or 
              "sin http" in msg_lower or "sin evidencia" in msg_lower or
              "sin comprobación" in msg_lower or "no modifiques" in msg_lower) and
            ("estado real" in msg_lower or "verdadero estado" in msg_lower)) or
            # FIX: Bloquear "verifica estado real" sin "realmente"
            (("verifica" in msg_lower or "revisa" in msg_lower or "comprueba" in msg_lower) and
             "estado real" in msg_lower and
             any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"]))
        )
        
        if is_epistemic_question:
            # Block template emission - respond epistemically instead
            epistemic_response = (
                "No puedo afirmar el estado real del dashboard sin verificación HTTP/tool actual. "
                "Puedo inferir por contexto, pero no verificarlo."
            )
            return {
                "success": True,
                "content": epistemic_response,
                "response": epistemic_response,
                "model": "agent_orav",
                "model_used": "agent_orav",
                "agent_steps": 1,
                "agent_status": "epistemic_restraint",
            }
        
        # B3 FIX: Bloquear cuando se pide verificación real explícita con herramientas
        has_real_verification_request = (
            ("verifica realmente" in msg_lower or 
             "verifiques realmente" in msg_lower or
             "revisa realmente" in msg_lower or
             "comprueba realmente" in msg_lower or
             "usando herramientas" in msg_lower or
             "usa herramientas" in msg_lower) and
            any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
        )
        
        if has_real_verification_request:
            # B3: Bloquear template - requiere verificación real o confirmación de herramientas
            b3_response = (
                "Para verificar realmente el dashboard necesito usar herramientas HTTP. "
                "¿Confirmas que puedo ejecutar verificación real del endpoint?"
            )
            return {
                "success": True,
                "content": b3_response,
                "response": b3_response,
                "model": "agent_orav",
                "model_used": "agent_orav",
                "agent_steps": 1,
                "agent_status": "tool_confirmation_required",
            }
        
        # B3-v2 FIX: Bloquear cuando se pide contenido/análisis del dashboard (no solo infraestructura)
        asks_for_dashboard_content = (
            any(x in msg_lower for x in ["analiza", "muestra", "dime", "explica", "describe", "cuéntame", "cuentame"]) and
            "dashboard" in msg_lower and
            not any(x in msg_lower for x in ["infraestructura", "servidor", "host", "puerto", "url", "estatus simple", "estado simple"])
        )
        
        if asks_for_dashboard_content:
            # El usuario quiere ver/analizar el contenido del dashboard, no solo confirmar que existe
            content_response = (
                "Para analizar/mostrar el contenido real del dashboard necesito hacer HTTP a la interfaz. "
                "El template solo muestra infraestructura. ¿Quieres que verifique el endpoint real con herramientas?"
            )
            return {
                "success": True,
                "content": content_response,
                "response": content_response,
                "model": "agent_orav",
                "model_used": "agent_orav",
                "agent_steps": 1,
                "agent_status": "tool_confirmation_required",
            }
        
        direct = session._dashboard_status_fastpath()
        full = direct.get("content") or "No pude verificar el dashboard."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["edge validation", "edge_validation", "estado del edge", "estado de edge"]):
        direct = session._cmd_edge()
        full = direct.get("content") or "No pude resumir edge validation."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["ranking v2", "strategy ranking", "ranking actual", "estado del ranking"]):
        direct = session._cmd_ranking()
        full = direct.get("content") or "No pude resumir ranking."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["hipotesis", "hipótesis", "hypothesis", "sintesis post-trade", "síntesis post-trade"]):
        direct = session._cmd_hypothesis()
        full = direct.get("content") or "No pude resumir hipótesis."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["post-trade", "post trade", "analisis post-trade", "análisis post-trade"]):
        direct = session._cmd_posttrade()
        full = direct.get("content") or "No pude resumir post-trade."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["security posture", "postura de seguridad", "estado de seguridad", "seguridad del sistema"]):
        direct = session._cmd_security()
        full = direct.get("content") or "No pude resumir seguridad."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["session memory", "memoria de sesion", "memoria de sesión", "contexto de la sesion", "contexto de la sesión"]):
        direct = session._cmd_memory()
        full = direct.get("content") or "No pude resumir memoria de sesión."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["control layer", "change control", "change scorecard", "scorecard de cambios", "control de cambios"]):
        direct = session._cmd_control()
        full = direct.get("content") or "No pude resumir control de cambios."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["estado de autonomia", "estado del loop autonomo", "estado del loop autónomo", "autonomy status", "autonomia actual"]):
        direct = session._cmd_autonomy()
        full = direct.get("content") or "No pude resumir autonomía."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["estado del sistema", "status del sistema", "system status", "resumen del sistema"]):
        direct = session._cmd_status()
        full = direct.get("content") or "No pude resumir el sistema."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["learning loop", "loop de aprendizaje", "decisiones de aprendizaje", "learning decisions", "estado del learning"]):
        direct = session._cmd_learning()
        full = direct.get("content") or "No pude resumir learning loop."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["catalogo activo", "catálogo activo", "active catalog", "estrategias operativas", "estrategias activas"]):
        direct = session._cmd_catalog()
        full = direct.get("content") or "No pude resumir catálogo activo."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    if any(x in msg for x in ["context edge", "context-edge", "edge por contexto", "edge de contexto", "validacion por contexto", "validación por contexto"]):
        direct = session._cmd_context_edge()
        full = direct.get("content") or "No pude resumir context edge."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    # P-OP56: Trading analysis fastpath — combines trade + strategy + signals + pipeline
    if any(x in msg for x in [
        "estado del trading", "estado actual del trading", "analiza el trading",
        "analiza el estado actual del trading", "estado de trading",
        "trading status", "analisis de trading", "análisis de trading",
        "resumen de trading", "como va el trading", "cómo va el trading",
    ]):
        direct = session._cmd_trading_analysis()
        full = direct.get("content") or "No pude resumir el estado de trading."
        return {
            "success": direct.get("success", False),
            "content": full, "response": full,
            "model": "agent_orav", "model_used": "agent_orav",
            "agent_steps": 1, "agent_status": "tool_backed_fastpath",
        }
    
    from brain_v9.agent.loop import AgentLoop, MetaPlanner
    from brain_v9.agent.tools import build_standard_executor
    
    if session._executor is None:
        session._executor = build_standard_executor()
        session.logger.info("ToolExecutor: %d tools", len(session._executor.list_tools()))
    
    # Phase H: Decide route — MetaPlanner for complex tasks, AgentLoop for simple/medium
    probe_loop = AgentLoop(session.llm, session._executor)
    complexity = probe_loop._classify_complexity(message)
    session.logger.info("Task complexity: %s for: %s", complexity, message[:80])
    
    # Token-aware agent context (replaces old [-4:] slice)
    # Agent prompt is large (~1500 tokens with tool examples), so
    # we give history a small budget — enough for ~4-6 short messages.
    agent_history = session._truncate_to_budget(
        session.memory.get_context(), budget_tokens=800
    )
    temporal_query = session._is_temporal_query(message)
    
    agent_chain = model_priority if model_priority in {
        "agent", "agent_frontier", "agent_frontier_legacy", "agent_legacy",
        "code", "code_legacy", "codex",
    } else "agent_frontier"
    
    base_context = {
        "session_id": session.session_id,
        "history": agent_history,
        "model_priority": agent_chain,
        "temporal_query": temporal_query,
    }
    
    try:
        from brain_v9.governance.execution_gate import push_chat_session, pop_chat_session
    except Exception:
        push_chat_session = pop_chat_session = None
    
    gate_token = None
    if push_chat_session is not None:
        gate_token = push_chat_session(session.session_id)
    try:
        if complexity == "complex":
            # Phase H2: MetaPlanner decomposes into sub-tasks
            planner = MetaPlanner(session.llm, session._executor)
            agent_result = await asyncio.wait_for(
                planner.run(task=message, context=base_context),
                timeout=45,  # BOR-4B: non-blocking guard for interactive chat
            )
            meta_history = []
            for sr in planner.subtask_results:
                meta_history.extend(sr.get("history", []))
            history = meta_history
        else:
            # Simple/medium: direct AgentLoop
            loop = probe_loop
            agent_result = await asyncio.wait_for(
                loop.run(task=message, context=base_context),
                timeout=35,  # BOR-4B: non-blocking guard for interactive chat
            )
            history = loop.get_history()
    except asyncio.TimeoutError:
        session.logger.warning("Agent route timeout for session %s task: %s", session.session_id, message[:80])
        agent_result = {
            "success": False,
            "result": None,
            "steps": 0,
            "summary": "agent_timeout",
            "status": "timeout",
        }
        history = []
    finally:
        if gate_token is not None and pop_chat_session is not None:
            pop_chat_session(gate_token)
    
    steps  = agent_result.get("steps", 0)
    status = agent_result.get("status", "?")
    complexity_tag = agent_result.get("complexity", complexity)
    
    # Collect tool outputs
    tool_actions = []
    for step in history:
        for action in step.get("actions", []):
            tool_actions.append(action)
    
    # Phase E: Prefer LLM-synthesized answer when available
    synthesized = agent_result.get("synthesized_answer")
    
    # BOR-2: Clean Agent Failure Fallback — LLM fallback for ghost/max_steps/timeout
    # BOR-3B: stable fallback chain; avoid "auto" because it can resolve to weak local llm.
    # BOR-3C: direct stable fallback via llm.query() to bypass _select_llm_chain re-mapping.
    if not tool_actions and session._is_agent_execution_failure(agent_result):
        fallback_priority = "chat"
        fallback_messages = [
            {
                "role": "system",
                "content": (
                    "Eres Brain V9. El agente de herramientas no pudo ejecutar acciones reales. "
                    "Responde al usuario directamente, en español, de forma útil, breve y honesta. "
                    "No afirmes que leíste archivos, ejecutaste comandos o revisaste logs si no ocurrió."
                ),
            },
            {"role": "user", "content": message[:1500]},
        ]
        llm_raw = await session.llm.query(fallback_messages, model_priority=fallback_priority)
        llm_result = {
            "success": bool(llm_raw.get("success")),
            "content": llm_raw.get("content") or "",
            "response": llm_raw.get("content") or "",
            "model": llm_raw.get("model_used") or llm_raw.get("model", "llm"),
            "model_used": llm_raw.get("model_used") or llm_raw.get("model", "llm"),
        }
        notice = session._agent_failure_notice(status)
        llm_text = session._sanitize_user_visible_response(llm_result.get("content") or "")
        if llm_text:
            content = f"{notice}\n\n{llm_text}"
        else:
            content = notice
        return {
            "success": bool(llm_result.get("success")),
            "content": content,
            "response": content,
            "model": llm_result.get("model_used") or llm_result.get("model", "llm"),
            "model_used": llm_result.get("model_used") or llm_result.get("model", "llm"),
            "route": "agent_fallback_llm",
            "original_route": "agent",
            "agent_status": status,
            "agent_steps": steps,
            "agent_success": False,
            "fallback_success": bool(llm_result.get("success")),
        }
    
    if synthesized:
        full = session._sanitize_user_visible_response(synthesized)
    elif tool_actions:
        full = session._render_operational_agent_summary(
            message,
            tool_actions,
            steps=steps,
            status=status,
        )
        full = session._sanitize_user_visible_response(full)
    elif agent_result.get("result"):
        raw = agent_result["result"]
        full = raw if isinstance(raw, str) else str(raw)
        status_note = agent_result.get("status")
        if status_note in ("ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"):
            full = session._render_agent_failure_reply(status_note, full)
        else:
            full = session._sanitize_user_visible_response(full)
    else:
        if status in ("ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"):
            full = session._render_agent_failure_reply(status)
        else:
            try:
                fallback_text = await session._llm_direct_fallback(message)
                full = session._sanitize_user_visible_response(fallback_text) if fallback_text else (
                    f"No pude resolver esta consulta en este turno.\n"
                    f"Reformula la pregunta o pide una verificacion concreta."
                )
            except Exception:
                full = (
                    f"No pude resolver esta consulta en este turno.\n"
                    f"Reformula la pregunta o pide una verificacion concreta."
                )
    
    # Phase G: Check for gate-blocked actions and add hint
    gate_hint = ""
    for act in tool_actions:
        output = act.get("output") if isinstance(act, dict) else getattr(act, "output", None)
        if isinstance(output, dict) and output.get("gate_blocked"):
            pending_id = output.get("pending_id", "")
            risk = output.get("risk", "?")
            action_type = output.get("action", "?")
            gate_hint = (
                f"\n\n--- Accion pendiente de aprobacion ---\n"
                f"Riesgo: {risk} | Accion: {action_type}\n"
                f"ID: {pending_id}\n"
                f"Usa /approve para aprobar o /reject {pending_id} para rechazar.\n"
                f"Usa /pending para ver todas las acciones pendientes."
            )
            break
    full += gate_hint
    full = session._sanitize_user_visible_response(full)
    
    extractive_fallback = full.strip().lower().startswith("*[resumen extractivo")
    salvaged = None
    if extractive_fallback or session._looks_like_canned_failure(full):
        salvaged = await session._llm_agent_salvage(
            message,
            status=status,
            steps=steps,
            tool_actions=tool_actions,
            current_text=full,
        )
        if salvaged:
            full = session._sanitize_user_visible_response(salvaged["content"])
            extractive_fallback = False
    return {
        "success": (bool(agent_result.get("success", True)) or bool(salvaged)) and status not in (
            "ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"
        ) and not extractive_fallback,
        "content": full, "response": full,
        "model": "agent_orav", "model_used": (salvaged or {}).get("model_used", "agent_orav"),
        "agent_steps": steps, "agent_status": status,
    }
