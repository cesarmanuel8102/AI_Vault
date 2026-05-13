"""
Brain V9 - Roadmap governance
Reconciliación canónica de roadmaps legacy y autopromoción del roadmap BL.
"""
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.brain.utility import write_utility_snapshots
from brain_v9.brain.phase_acceptance_engine import ensure_phase_specs, evaluate_phase_acceptance as evaluate_phase_acceptance_from_specs, load_phase_spec

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ROOMS_PATH = STATE_PATH / "rooms"

FILES = {
    "roadmap": STATE_PATH / "roadmap.json",
    "cycle": STATE_PATH / "next_level_cycle_status_latest.json",
    "utility_latest": STATE_PATH / "utility_u_latest.json",
    "utility_gate": STATE_PATH / "utility_u_promotion_gate_latest.json",
    "strategy_ranking": STATE_PATH / "strategy_engine" / "strategy_ranking_latest.json",
    "trading_policy": STATE_PATH / "trading_autonomy_policy.json",
    "legacy_runtime": STATE_PATH / "roadmap_runtime_v2.json",
    "legacy_dashboard": STATE_PATH / "dashboard_roadmap.json",
    "legacy_dashboard_bridge": STATE_PATH / "dashboard_roadmap_bridge_px_latest.json",
    "legacy_financial": STATE_PATH / "roadmap_financial_motor_v1.json",
    "legacy_registry": STATE_PATH / "roadmap_registry_v2.json",
    "legacy_console_quality": STATE_PATH / "roadmaps" / "brain_console_operator_quality_v2.json",
    "legacy_binary_paper": STATE_PATH / "roadmaps" / "brain_binary_paper_validation_v1.json",
    "legacy_self_improvement": STATE_PATH / "roadmaps" / "brain_governed_self_improvement_engine_v2.json",
    "legacy_acceptance_framework": STATE_PATH / "roadmaps" / "brain_acceptance_and_evidence_framework_v2.json",
    "legacy_reconciliation": STATE_PATH / "roadmap_legacy_reconciliation_latest.json",
    "promotion_state": STATE_PATH / "roadmap_promotion_state_latest.json",
    "governance_status": STATE_PATH / "roadmap_governance_status.json",
    "development_status": STATE_PATH / "roadmap_development_status_latest.json",
}

BL_NEXT_ITEMS = {
    "BL-01": "align_ssot_runtime_and_control_plane_canonically",
    "BL-02": "make_utility_u_operational_for_scoring_gates_and_capital_logic",
    "BL-03": "stabilize_financial_telemetry_and_ingestion_quality",
    "BL-04": "expand_governed_workers_and_useful_autonomy",
    "BL-05": "version_missions_episodes_and_artifacts",
    "BL-06": "formalize_capital_layers_and_promotion_gates",
    "BL-07": "strengthen_local_first_routing_and_pragmatic_sovereignty",
    "BL-08": "maintain_operational_readiness_and_auditability",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_state() -> Dict[str, Any]:
    return {
        "roadmap": read_json(FILES["roadmap"], {}),
        "cycle": read_json(FILES["cycle"], {}),
        "utility_latest": read_json(FILES["utility_latest"], {}),
        "utility_gate": read_json(FILES["utility_gate"], {}),
        "strategy_ranking": read_json(FILES["strategy_ranking"], {}),
        "trading_policy": read_json(FILES["trading_policy"], {}),
    }


def _legacy_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "label": "runtime_v2",
            "path": FILES["legacy_runtime"],
            "decision": "archived_certified",
            "reason": "Runtime v2 ya quedó completado y aporta solo como baseline histórico certificado para hardening.",
            "mapped_to": ["BL-08"],
            "visibility": "historical_only",
        },
        {
            "label": "dashboard_px",
            "path": FILES["legacy_dashboard"],
            "decision": "legacy_mapped_to_bl",
            "reason": "La productización y observabilidad siguen aportando, pero ya no deben correr como roadmap paralelo; quedan absorbidas en BL.",
            "mapped_to": ["BL-03", "BL-04", "BL-08"],
            "visibility": "mapped_visible",
        },
        {
            "label": "dashboard_px_projection",
            "path": FILES["legacy_dashboard_bridge"],
            "decision": "legacy_mapped_to_bl",
            "reason": "La proyección PX del dashboard queda visible solo como vista derivada del legado, no como plan activo independiente.",
            "mapped_to": ["BL-03", "BL-04", "BL-08"],
            "visibility": "mapped_visible",
        },
        {
            "label": "financial_motor_v1",
            "path": FILES["legacy_financial"],
            "decision": "legacy_absorbed_into_bl",
            "reason": "La intención financiera principal ya vive en BL; mantenerlo activo aparte generaría dos narrativas operativas en conflicto.",
            "mapped_to": ["BL-02", "BL-03", "BL-06"],
            "visibility": "absorbed_reference",
        },
        {
            "label": "console_quality_v2",
            "path": FILES["legacy_console_quality"],
            "decision": "legacy_mapped_to_bl",
            "reason": "La calidad operatoria de consola sigue importando, pero hoy se materializa a través de workers gobernados, evidencias y observabilidad en BL.",
            "mapped_to": ["BL-04", "BL-08"],
            "visibility": "mapped_visible",
        },
        {
            "label": "binary_paper_validation_v1",
            "path": FILES["legacy_binary_paper"],
            "decision": "legacy_absorbed_into_bl",
            "reason": "La validación paper binaria se volvió parte del strategy engine, scorecards y evaluation layers del Brain financiero actual.",
            "mapped_to": ["BL-02", "BL-03", "BL-06"],
            "visibility": "absorbed_reference",
        },
        {
            "label": "governed_self_improvement_engine_v2",
            "path": FILES["legacy_self_improvement"],
            "decision": "legacy_mapped_to_bl",
            "reason": "Su aporte sigue vigente como patrón de gobernanza y aceptación, pero ya no debe vivir como motor maestro separado.",
            "mapped_to": ["BL-04", "BL-08"],
            "visibility": "mapped_visible",
        },
        {
            "label": "acceptance_and_evidence_framework_v2",
            "path": FILES["legacy_acceptance_framework"],
            "decision": "legacy_mapped_to_bl",
            "reason": "El framework de aceptación sigue aportando, pero como soporte común del roadmap BL y no como plan primario.",
            "mapped_to": ["BL-08"],
            "visibility": "mapped_visible",
        },
    ]


def reconcile_legacy_roadmaps() -> Dict[str, Any]:
    now = _utc_now()
    roadmap = read_json(FILES["roadmap"], {})
    canonical_id = roadmap.get("roadmap_id") or roadmap.get("active_program") or "brain_lab_transition_v3"
    canonical_phase = roadmap.get("current_phase")
    reconciled_rows = []

    for item in _legacy_definitions():
        payload = read_json(item["path"], {})
        if not payload:
            reconciled_rows.append({
                "label": item["label"],
                "path": str(item["path"]),
                "exists": False,
                "decision": item["decision"],
                "reason": f"Archivo no encontrado. {item['reason']}",
                "mapped_to": item["mapped_to"],
                "visibility": item["visibility"],
            })
            continue

        payload["legacy_governance"] = {
            "decision": item["decision"],
            "reason": item["reason"],
            "mapped_to_bl": item["mapped_to"],
            "visibility": item["visibility"],
            "canonical_owner_roadmap": canonical_id,
            "canonical_owner_phase": canonical_phase,
            "autopromotion_managed_by": canonical_id,
            "reconciled_utc": now,
        }
        write_json(item["path"], payload)
        reconciled_rows.append({
            "label": item["label"],
            "roadmap_id": payload.get("roadmap_id") or payload.get("active_roadmap"),
            "current_phase": payload.get("current_phase") or payload.get("phase"),
            "current_stage": payload.get("current_stage") or payload.get("stage") or payload.get("status"),
            "path": str(item["path"]),
            "exists": True,
            "decision": item["decision"],
            "reason": item["reason"],
            "mapped_to": item["mapped_to"],
            "visibility": item["visibility"],
        })

    registry = read_json(FILES["legacy_registry"], {})
    if registry:
        registry["legacy_governance"] = {
            "registry_state": "reconciled_to_canonical_bl",
            "canonical_active_roadmap": canonical_id,
            "reconciled_utc": now,
            "note": "Los roadmaps legacy siguen preservados, pero la promoción autónoma ya se gobierna solo desde BL.",
        }
        registry["program_id"] = canonical_id
        registry["active_roadmap"] = canonical_id
        rows_by_id = {row["roadmap_id"]: row for row in reconciled_rows if row.get("roadmap_id")}
        updated_entries = []
        for entry in registry.get("roadmaps", []):
            new_entry = dict(entry)
            if new_entry.get("roadmap_id") in rows_by_id:
                new_entry["state"] = rows_by_id[new_entry["roadmap_id"]]["decision"]
            elif new_entry.get("state") == "active":
                new_entry["state"] = "legacy_superseded"
            updated_entries.append(new_entry)
        if not any(e.get("roadmap_id") == canonical_id for e in updated_entries):
            updated_entries.append({
                "roadmap_id": canonical_id,
                "path": str(FILES["roadmap"]),
                "state": "active_canonical",
            })
        registry["roadmaps"] = updated_entries
        write_json(FILES["legacy_registry"], registry)

    summary = {
        "archived_certified": sum(1 for row in reconciled_rows if row["decision"] == "archived_certified"),
        "legacy_mapped_to_bl": sum(1 for row in reconciled_rows if row["decision"] == "legacy_mapped_to_bl"),
        "legacy_absorbed_into_bl": sum(1 for row in reconciled_rows if row["decision"] == "legacy_absorbed_into_bl"),
    }
    payload = {
        "schema_version": "roadmap_legacy_reconciliation_v1",
        "updated_utc": now,
        "canonical_active_roadmap": canonical_id,
        "canonical_current_phase": canonical_phase,
        "summary": summary,
        "legacy_roadmaps": reconciled_rows,
        "registry_path": str(FILES["legacy_registry"]),
    }
    write_json(FILES["legacy_reconciliation"], payload)
    return payload

def evaluate_phase_acceptance(state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state or _load_state()
    roadmap = state["roadmap"]
    current_phase = roadmap.get("current_phase")
    return evaluate_phase_acceptance_from_specs(current_phase, state)


def _recalculate_counts(work_items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"total": len(work_items), "done": 0, "in_progress": 0, "pending": 0, "blocked": 0}
    for item in work_items:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _phase_artifact_path(room_id: str | None, phase_id: str, artifact_kind: str) -> Path:
    room = room_id or f"phase_{phase_id.lower().replace('-', '_')}"
    suffix = f"{phase_id.lower().replace('-', '')}_{artifact_kind}.json"
    return ROOMS_PATH / room / suffix


def _current_phase_item(roadmap: Dict[str, Any], phase_id: str | None) -> Dict[str, Any]:
    return next((item for item in roadmap.get("work_items", []) if item.get("id") == phase_id), {})


def _stringify_detail(detail: Any) -> str:
    if detail is None:
        return "sin_detalle"
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        chunks = []
        for key, value in detail.items():
            if value not in (None, "", [], {}):
                chunks.append(f"{key}={value}")
        return " · ".join(chunks) if chunks else "sin_detalle"
    return str(detail)


def _check_repair_hint(check: Dict[str, Any]) -> str:
    kind = check.get("kind")
    source = check.get("source")
    path = check.get("path")
    detail = check.get("detail")
    if kind == "file_exists":
        file_path = (detail or {}).get("file_path") if isinstance(detail, dict) else None
        return f"Emitir o restaurar el artifact requerido: {file_path or check.get('file_path')}"
    if kind == "directory_file_count_gte":
        return f"Poblar y versionar artifacts en {check.get('directory')} hasta alcanzar el mínimo requerido."
    if kind == "recent_iso_utc":
        return f"Refrescar la fuente {source}.{path} dentro de la ventana de frescura exigida."
    if kind == "present":
        return f"Poblar el campo canónico {source}.{path}."
    if kind == "bool_true":
        return f"Hacer que la regla {source}.{path} quede explícitamente en true."
    if kind == "in_set":
        return f"Alinear {source}.{path} a uno de los valores permitidos {check.get('allowed')}."
    if kind == "list_type":
        return f"Materializar {source}.{path} como lista válida."
    if kind == "list_length_gte":
        return f"Incrementar la evidencia en {source}.{path} hasta alcanzar el mínimo requerido."
    if kind == "list_last_field_in_set":
        return f"Hacer que el último registro en {source}.{path} termine con {check.get('field')} dentro del conjunto permitido."
    if kind == "list_any_field_in_set":
        return f"Inyectar evidencia en {source}.{path} donde {check.get('field')} coincida con uno de los valores requeridos."
    if kind == "numeric_gte":
        return f"Elevar {source}.{path} hasta al menos {check.get('min')}."
    return "Investigar y resolver la evidencia faltante del check."


def _build_meta_brain_handoff(
    roadmap: Dict[str, Any],
    phase_item: Dict[str, Any],
    promotion_payload: Dict[str, Any],
    failed_checks: List[Dict[str, Any]],
    work_status: str,
    current_work_items: List[str],
) -> str:
    phase_id = roadmap.get("current_phase")
    phase_title = roadmap.get("active_title")
    objective = phase_item.get("objective")
    deliverable = phase_item.get("deliverable")
    promotion_state = promotion_payload.get("promotion_state")
    lines = [
        f"roadmap={roadmap.get('roadmap_id') or roadmap.get('active_program')}",
        f"phase={phase_id} · title={phase_title}",
        f"stage={roadmap.get('current_stage')} · status={work_status} · promotion_state={promotion_state}",
        f"objective={objective or 'n/a'}",
        f"deliverable={deliverable or 'n/a'}",
    ]
    if current_work_items:
        lines.append("current_work=" + " | ".join(current_work_items))
    if failed_checks:
        lines.append("blocking_checks=")
        for check in failed_checks:
            lines.append(
                f"- {check.get('id')}: {_stringify_detail(check.get('detail'))} | hint={_check_repair_hint(check)}"
            )
    else:
        lines.append("blocking_checks=none")
    return "\n".join(lines)


def _build_development_status(
    roadmap: Dict[str, Any],
    promotion_payload: Dict[str, Any],
    current_phase_spec: Dict[str, Any],
) -> Dict[str, Any]:
    phase_id = roadmap.get("current_phase")
    phase_item = _current_phase_item(roadmap, phase_id)
    acceptance = promotion_payload.get("acceptance", {})
    checks = acceptance.get("checks", [])
    failed_checks = [check for check in checks if not check.get("passed")]
    promotion_state = promotion_payload.get("promotion_state")
    evaluator_status = current_phase_spec.get("evaluator_status")

    if roadmap.get("current_stage") == "done" and promotion_state == "terminal_phase_accepted":
        work_status = "completed"
        current_work_summary = "Roadmap BL completado y aceptado terminalmente."
        last_error = None
        current_work_items = [
            "mantener auditabilidad y readiness operativa",
            "preservar contracts y evidencias terminales",
        ]
    elif promotion_state == "phase_active_spec_draft":
        work_status = "needs_phase_spec"
        current_work_summary = "Formalizando evaluator, contracts y criterios de aceptación de la fase."
        last_error = acceptance.get("acceptance_reason")
        current_work_items = [
            "emitir spec implementada por fase",
            "materializar artifacts canónicos faltantes",
            "re-ejecutar acceptance tras completar evidencia",
        ]
    elif failed_checks:
        work_status = "blocked"
        current_work_summary = "Intentando cerrar la fase, pero acceptance sigue fallando por evidencia o contratos faltantes."
        last_error = "; ".join(f"{check.get('id')}: {_stringify_detail(check.get('detail'))}" for check in failed_checks[:3])
        current_work_items = [_check_repair_hint(check) for check in failed_checks[:5]]
    elif promotion_state == "promoted":
        work_status = "transitioning"
        current_work_summary = "Fase aceptada y promocionada; activando la siguiente fase."
        last_error = None
        current_work_items = [
            f"activar {promotion_payload.get('to_phase')}",
            "escribir artifacts de completion y activation",
        ]
    else:
        work_status = "active"
        current_work_summary = "Ejecutando la fase actual y refrescando acceptance de forma autónoma."
        last_error = acceptance.get("acceptance_reason") if acceptance.get("accepted") is False else None
        current_work_items = [
            "refrescar utility y governance",
            "verificar checks de fase",
            "promover cuando la aceptación sea suficiente",
        ]

    blockers = [
        {
            "check_id": check.get("id"),
            "kind": check.get("kind"),
            "source": check.get("source"),
            "path": check.get("path"),
            "detail": check.get("detail"),
            "repair_hint": _check_repair_hint(check),
        }
        for check in failed_checks
    ]
    evidence_paths = sorted({
        str(path)
        for path in [
            promotion_payload.get("completion_artifact"),
            current_phase_spec.get("spec_path"),
            FILES["roadmap"],
            FILES["promotion_state"],
            FILES["governance_status"],
            *[
                check.get("detail", {}).get("file_path")
                for check in failed_checks
                if isinstance(check.get("detail"), dict)
            ],
        ]
        if path
    })
    return {
        "schema_version": "roadmap_development_status_v1",
        "updated_utc": promotion_payload.get("updated_utc") or _utc_now(),
        "roadmap_id": roadmap.get("roadmap_id") or roadmap.get("active_program"),
        "phase_id": phase_id,
        "phase_title": roadmap.get("active_title"),
        "phase_objective": phase_item.get("objective"),
        "phase_deliverable": phase_item.get("deliverable"),
        "room_id": phase_item.get("room_id"),
        "current_stage": roadmap.get("current_stage"),
        "work_status": work_status,
        "promotion_state": promotion_state,
        "evaluator_status": evaluator_status,
        "acceptance_mode": current_phase_spec.get("acceptance_mode"),
        "accepted": acceptance.get("accepted"),
        "current_work_summary": current_work_summary,
        "current_work_items": current_work_items,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "last_error": last_error,
        "meta_brain_handoff": _build_meta_brain_handoff(
            roadmap=roadmap,
            phase_item=phase_item,
            promotion_payload=promotion_payload,
            failed_checks=failed_checks,
            work_status=work_status,
            current_work_items=current_work_items,
        ),
        "next_recommended_actions": [item.get("repair_hint") for item in blockers[:5]] if blockers else [],
        "evidence_paths": evidence_paths,
    }


def _promote_bl_phase(roadmap: Dict[str, Any], cycle: Dict[str, Any], acceptance: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    promote_to = acceptance.get("promote_to")
    work_items = deepcopy(roadmap.get("work_items", []))
    old_phase = roadmap.get("current_phase")
    now = _utc_now()

    previous_item = next((item for item in work_items if item.get("id") == old_phase), None)
    next_item = next((item for item in work_items if item.get("id") == promote_to), None)

    if previous_item:
        previous_item["status"] = "done"
        previous_item["completed_utc"] = now
        previous_item["autopromoted_completion"] = True
        previous_item["result_note"] = acceptance.get("acceptance_reason")
    if next_item:
        next_item["status"] = "in_progress"
        next_item["started_utc"] = now
        next_item["autopromoted_activation"] = True

    counts = _recalculate_counts(work_items)
    updated_roadmap = deepcopy(roadmap)
    updated_roadmap["current_phase"] = promote_to
    updated_roadmap["current_stage"] = "in_progress"
    updated_roadmap["active_title"] = next_item.get("title") if next_item else roadmap.get("active_title")
    updated_roadmap["next_item"] = BL_NEXT_ITEMS.get(promote_to, roadmap.get("next_item"))
    updated_roadmap["counts"] = counts
    updated_roadmap["phase_progress"] = {
        "done": counts["done"],
        "in_progress": counts["in_progress"],
        "pending": counts["pending"],
    }
    updated_roadmap["work_items"] = work_items
    updated_roadmap["updated_utc"] = now
    updated_roadmap["reconciled_at"] = now
    updated_roadmap["reconciled_reason"] = f"Autopromoción autónoma desde {old_phase} hacia {promote_to} tras acceptance evaluator."

    updated_cycle = deepcopy(cycle)
    updated_cycle["updated_utc"] = now
    updated_cycle["current_phase"] = promote_to
    updated_cycle["phase"] = promote_to
    updated_cycle["phase_id"] = promote_to
    updated_cycle["current_stage"] = "in_progress"
    updated_cycle["stage"] = "in_progress"
    updated_cycle["active_title"] = next_item.get("title") if next_item else cycle.get("active_title")
    updated_cycle["next_item"] = BL_NEXT_ITEMS.get(promote_to, cycle.get("next_item"))
    updated_cycle["room_id"] = next_item.get("room_id") if next_item else cycle.get("room_id")
    updated_cycle["roadmap_total"] = counts["total"]
    updated_cycle["roadmap_done"] = counts["done"]
    updated_cycle["roadmap_pending"] = counts["pending"]
    updated_cycle["roadmap_in_progress"] = counts["in_progress"]
    updated_cycle["roadmap_blocked"] = counts["blocked"]
    updated_cycle["done"] = counts["done"]
    updated_cycle["total"] = counts["total"]
    updated_cycle["reconciled_at"] = now
    updated_cycle["reconciled_reason"] = f"Autopromoción autónoma desde {old_phase} hacia {promote_to}."

    completion_artifact_path = _phase_artifact_path(previous_item.get("room_id") if previous_item else None, old_phase, "complete")
    activation_artifact_path = _phase_artifact_path(next_item.get("room_id") if next_item else None, promote_to, "activation")

    completion_artifact = {
        "schema_version": "brain_lab_phase_completion_v1",
        "phase_id": old_phase,
        "completed_utc": now,
        "accepted": True,
        "autopromoted": True,
        "promoted_to": promote_to,
        "acceptance": acceptance,
        "roadmap_path": str(FILES["roadmap"]),
        "cycle_path": str(FILES["cycle"]),
    }
    activation_artifact = {
        "schema_version": "brain_lab_phase_activation_v1",
        "phase_id": promote_to,
        "activated_utc": now,
        "activation_mode": "autonomous_roadmap_promotion",
        "source_phase": old_phase,
        "room_id": updated_cycle.get("room_id"),
        "next_item": updated_roadmap.get("next_item"),
    }
    return updated_roadmap, updated_cycle, {
        "completion_artifact_path": completion_artifact_path,
        "activation_artifact_path": activation_artifact_path,
        "completion_artifact": completion_artifact,
        "activation_artifact": activation_artifact,
    }


def _complete_terminal_phase(roadmap: Dict[str, Any], cycle: Dict[str, Any], acceptance: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    current_phase = roadmap.get("current_phase")
    work_items = deepcopy(roadmap.get("work_items", []))
    now = _utc_now()

    current_item = next((item for item in work_items if item.get("id") == current_phase), None)
    if current_item:
        current_item["status"] = "done"
        current_item["completed_utc"] = now
        current_item["autonomous_terminal_acceptance"] = True
        current_item["result_note"] = acceptance.get("acceptance_reason")

    counts = _recalculate_counts(work_items)
    updated_roadmap = deepcopy(roadmap)
    updated_roadmap["current_stage"] = "done"
    updated_roadmap["next_item"] = None
    updated_roadmap["counts"] = counts
    updated_roadmap["phase_progress"] = {
        "done": counts["done"],
        "in_progress": counts["in_progress"],
        "pending": counts["pending"],
    }
    updated_roadmap["work_items"] = work_items
    updated_roadmap["updated_utc"] = now
    updated_roadmap["reconciled_at"] = now
    updated_roadmap["reconciled_reason"] = f"Aceptación terminal autónoma de {current_phase}."

    updated_cycle = deepcopy(cycle)
    updated_cycle["updated_utc"] = now
    updated_cycle["current_stage"] = "done"
    updated_cycle["stage"] = "done"
    updated_cycle["next_item"] = None
    updated_cycle["roadmap_total"] = counts["total"]
    updated_cycle["roadmap_done"] = counts["done"]
    updated_cycle["roadmap_pending"] = counts["pending"]
    updated_cycle["roadmap_in_progress"] = counts["in_progress"]
    updated_cycle["roadmap_blocked"] = counts["blocked"]
    updated_cycle["done"] = counts["done"]
    updated_cycle["total"] = counts["total"]
    updated_cycle["reconciled_at"] = now
    updated_cycle["reconciled_reason"] = f"Aceptación terminal autónoma de {current_phase}."

    completion_artifact_path = _phase_artifact_path(current_item.get("room_id") if current_item else None, current_phase, "complete")
    completion_artifact = {
        "schema_version": "brain_lab_terminal_phase_completion_v1",
        "phase_id": current_phase,
        "completed_utc": now,
        "accepted": True,
        "terminal_phase": True,
        "acceptance": acceptance,
        "roadmap_path": str(FILES["roadmap"]),
        "cycle_path": str(FILES["cycle"]),
    }
    return updated_roadmap, updated_cycle, {
        "completion_artifact_path": completion_artifact_path,
        "completion_artifact": completion_artifact,
    }


def promote_roadmap_if_ready() -> Dict[str, Any]:
    state = _load_state()
    phase_specs = ensure_phase_specs()
    reconciliation = reconcile_legacy_roadmaps()
    acceptance = evaluate_phase_acceptance(state)
    roadmap = state["roadmap"]
    cycle = state["cycle"]
    previous_promotion = read_json(FILES["promotion_state"], {})
    now = _utc_now()
    current_phase = roadmap.get("current_phase")
    desired_next_item = BL_NEXT_ITEMS.get(current_phase)
    if desired_next_item and roadmap.get("next_item") != desired_next_item:
        roadmap["next_item"] = desired_next_item
        roadmap["updated_utc"] = now
        write_json(FILES["roadmap"], roadmap)
    if cycle.get("current_phase") == current_phase:
        cycle_changed = False
        if desired_next_item and cycle.get("next_item") != desired_next_item:
            cycle["next_item"] = desired_next_item
            cycle_changed = True
        if cycle.get("phase_id") != current_phase:
            cycle["phase_id"] = current_phase
            cycle_changed = True
        if cycle_changed:
            cycle["updated_utc"] = now
            write_json(FILES["cycle"], cycle)
    current_phase_item = next((item for item in roadmap.get("work_items", []) if item.get("id") == current_phase), {})
    current_activation_path = _phase_artifact_path(current_phase_item.get("room_id"), current_phase, "activation")
    if current_activation_path.exists():
        activation = read_json(current_activation_path, {})
        if desired_next_item and activation.get("next_item") != desired_next_item:
            activation["next_item"] = desired_next_item
            write_json(current_activation_path, activation)

    promotion_payload = {
        "schema_version": "roadmap_promotion_state_v1",
        "updated_utc": now,
        "canonical_active_roadmap": roadmap.get("roadmap_id") or roadmap.get("active_program"),
        "current_phase": roadmap.get("current_phase"),
        "current_stage": roadmap.get("current_stage"),
        "acceptance": acceptance,
        "legacy_reconciliation_path": str(FILES["legacy_reconciliation"]),
        "promotion_state": "not_ready",
        "promoted": False,
    }
    current_phase_spec = load_phase_spec(current_phase)
    completion_artifact_path = None
    activation_artifact_path = None
    previous_phase = previous_promotion.get("from_phase")
    previous_to_phase = previous_promotion.get("to_phase")
    if previous_phase:
        previous_item = next((item for item in roadmap.get("work_items", []) if item.get("id") == previous_phase), {})
        completion_artifact_path = _phase_artifact_path(previous_item.get("room_id"), previous_phase, "complete")
    if previous_to_phase:
        previous_next_item = next((item for item in roadmap.get("work_items", []) if item.get("id") == previous_to_phase), {})
        activation_artifact_path = _phase_artifact_path(previous_next_item.get("room_id"), previous_to_phase, "activation")
    completion_artifact = read_json(completion_artifact_path, {}) if completion_artifact_path else {}
    activation_artifact = read_json(activation_artifact_path, {}) if activation_artifact_path else {}
    previous_transition = previous_promotion.get("last_transition", {}) if previous_promotion else {}
    if previous_promotion.get("promoted") and previous_promotion.get("from_phase") and previous_promotion.get("to_phase"):
        previous_transition = {
            "from_phase": previous_promotion.get("from_phase"),
            "to_phase": previous_promotion.get("to_phase"),
            "updated_utc": previous_promotion.get("updated_utc"),
            "completion_artifact": previous_promotion.get("completion_artifact"),
            "activation_artifact": previous_promotion.get("activation_artifact"),
        }
    if previous_promotion:
        promotion_payload["last_transition"] = {
            "from_phase": previous_transition.get("from_phase") or previous_promotion.get("from_phase") or completion_artifact.get("phase_id"),
            "to_phase": previous_transition.get("to_phase") or previous_promotion.get("to_phase") or activation_artifact.get("phase_id"),
            "updated_utc": previous_transition.get("updated_utc") or previous_promotion.get("updated_utc") or completion_artifact.get("completed_utc"),
            "completion_artifact": previous_transition.get("completion_artifact") or previous_promotion.get("completion_artifact") or (str(completion_artifact_path) if completion_artifact_path and completion_artifact else None),
            "activation_artifact": previous_transition.get("activation_artifact") or previous_promotion.get("activation_artifact") or (str(activation_artifact_path) if activation_artifact_path and activation_artifact else None),
        }

    if current_phase_spec.get("evaluator_status") != "implemented":
        promotion_payload["promotion_state"] = "phase_active_spec_draft"
        promotion_payload["reason"] = acceptance.get("acceptance_reason")
    elif not acceptance.get("accepted"):
        promotion_payload["promotion_state"] = "not_ready"
        promotion_payload["reason"] = acceptance.get("acceptance_reason")
    elif not acceptance.get("promote_to"):
        updated_roadmap, updated_cycle, terminal_artifacts = _complete_terminal_phase(roadmap, cycle, acceptance)
        write_json(FILES["roadmap"], updated_roadmap)
        write_json(FILES["cycle"], updated_cycle)
        write_json(terminal_artifacts["completion_artifact_path"], terminal_artifacts["completion_artifact"])
        promotion_payload.update({
            "promotion_state": "terminal_phase_accepted",
            "current_phase": updated_roadmap.get("current_phase"),
            "current_stage": updated_roadmap.get("current_stage"),
            "reason": acceptance.get("acceptance_reason"),
            "terminal_phase": roadmap.get("current_phase"),
            "completion_artifact": str(terminal_artifacts["completion_artifact_path"]),
        })
        if previous_transition:
            promotion_payload["last_transition"] = previous_transition
        roadmap = updated_roadmap
        cycle = updated_cycle
        current_phase_spec = load_phase_spec(roadmap.get("current_phase"))
    else:
        updated_roadmap, updated_cycle, artifacts = _promote_bl_phase(roadmap, cycle, acceptance)
        write_json(FILES["roadmap"], updated_roadmap)
        write_json(FILES["cycle"], updated_cycle)
        write_json(artifacts["completion_artifact_path"], artifacts["completion_artifact"])
        write_json(artifacts["activation_artifact_path"], artifacts["activation_artifact"])
        promotion_payload.update({
            "promotion_state": "promoted",
            "promoted": True,
            "current_phase": updated_roadmap.get("current_phase"),
            "current_stage": updated_roadmap.get("current_stage"),
            "from_phase": roadmap.get("current_phase"),
            "to_phase": updated_roadmap.get("current_phase"),
            "reason": acceptance.get("acceptance_reason"),
            "completion_artifact": str(artifacts["completion_artifact_path"]),
            "activation_artifact": str(artifacts["activation_artifact_path"]),
            "last_transition": {
                "from_phase": roadmap.get("current_phase"),
                "to_phase": updated_roadmap.get("current_phase"),
                "updated_utc": now,
                "completion_artifact": str(artifacts["completion_artifact_path"]),
                "activation_artifact": str(artifacts["activation_artifact_path"]),
            },
        })
        roadmap = updated_roadmap
        cycle = updated_cycle
        current_phase_spec = load_phase_spec(roadmap.get("current_phase"))

    governance_status = {
        "schema_version": "roadmap_governance_status_v1",
        "updated_utc": now,
        "canonical": {
            "roadmap_id": roadmap.get("roadmap_id") or roadmap.get("active_program"),
            "current_phase": roadmap.get("current_phase"),
            "current_stage": roadmap.get("current_stage"),
            "active_title": roadmap.get("active_title"),
            "next_item": roadmap.get("next_item"),
            "counts": roadmap.get("counts", {}),
        },
        "promotion": promotion_payload,
        "phase_spec": {
            "phase_id": current_phase_spec.get("phase_id"),
            "spec_path": current_phase_spec.get("spec_path"),
            "evaluator_status": current_phase_spec.get("evaluator_status"),
            "acceptance_mode": current_phase_spec.get("acceptance_mode"),
            "checks_defined": len(current_phase_spec.get("checks", [])),
            "specs_dir": phase_specs.get("specs_dir"),
        },
        "legacy_reconciliation": {
            "summary": reconciliation.get("summary", {}),
            "legacy_roadmaps": reconciliation.get("legacy_roadmaps", []),
        },
    }
    development_status = _build_development_status(
        roadmap=roadmap,
        promotion_payload=promotion_payload,
        current_phase_spec=current_phase_spec,
    )
    governance_status["development_status"] = development_status

    write_json(FILES["promotion_state"], promotion_payload)
    write_json(FILES["governance_status"], governance_status)
    write_json(FILES["development_status"], development_status)
    return governance_status


def read_roadmap_governance_status() -> Dict[str, Any]:
    return read_json(FILES["governance_status"], {})
