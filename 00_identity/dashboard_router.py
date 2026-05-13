from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
UI_ROOT = ROOT / "ui" / "brain_console"
STATE_ROOT = Path(r"C:\AI_VAULT\tmp_agent\state")
ROOMS_ROOT = STATE_ROOT / "rooms"

BRAIN_BASE = "http://127.0.0.1:8010"
ADVISOR_BASE = "http://127.0.0.1:8030"

router = APIRouter(tags=["dashboard_vnext"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _room_dir(room_id: str) -> Path:
    rid = (room_id or "default").strip() or "default"
    return ROOMS_ROOT / rid


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path, max_chars: int = 120000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _tail_lines(path: Path, max_lines: int = 80) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-max_lines:]
    except Exception:
        return []


def _normalize_status(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in {"done", "complete", "completed", "success", "succeeded", "ok", "finished"}:
        return "done"
    if s in {"in_progress", "running", "executing", "active", "working", "started", "processing"}:
        return "in_progress"
    if s in {"blocked", "approval_required", "waiting_approval"}:
        return "blocked"
    if s in {"error", "failed", "fail", "exception", "degraded"}:
        return "error"
    if s in {"pending", "todo", "queued", "not_started", ""}:
        return "pending"
    return s


def _contract_payload() -> dict[str, Any]:
    files = {
        "contract": STATE_ROOT / "conversational_contract_v2.json",
        "clarification_policy": STATE_ROOT / "clarification_policy_v2.json",
        "response_presentation_policy": STATE_ROOT / "response_presentation_policy_v2.json",
        "examples": STATE_ROOT / "conversational_examples_v2.json",
    }
    payload: dict[str, Any] = {"ok": True, "version": "v2"}
    for key, path in files.items():
        payload[key] = _read_json(path)
    payload["bound"] = payload.get("contract") is not None
    payload["present_files"] = [str(p) for _, p in files.items() if p.exists()]
    return payload


def _extract_work_items(data: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def maybe_add(entry: Any) -> None:
        if not isinstance(entry, dict):
            return
        item_id = str(entry.get("id") or entry.get("key") or entry.get("name") or entry.get("title") or "").strip()
        title = str(entry.get("title") or entry.get("name") or entry.get("summary") or item_id or "").strip()
        status_raw = entry.get("status")
        status_norm = _normalize_status(status_raw)
        if not item_id and not title:
            return
        token = f"{item_id}|{title}"
        if token in seen:
            return
        seen.add(token)
        items.append({
            "id": item_id or title,
            "title": title or item_id,
            "status_raw": status_raw,
            "status_norm": status_norm,
            "stage": entry.get("stage") or entry.get("acceptance_stage"),
            "acceptance_stage": entry.get("acceptance_stage"),
            "owner": entry.get("owner"),
            "summary": entry.get("summary") or entry.get("objective") or entry.get("note"),
        })

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if isinstance(obj.get("work_items"), list):
                for wi in obj["work_items"]:
                    maybe_add(wi)
            if isinstance(obj.get("items"), list):
                if any(isinstance(x, dict) and ("status" in x or "title" in x or "id" in x) for x in obj["items"]):
                    for wi in obj["items"]:
                        maybe_add(wi)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return items[:200]


def _roadmap_payload() -> dict[str, Any]:
    candidates = [
        STATE_ROOT / "roadmap_brain_lab_20260310_resume_v1.json",
        STATE_ROOT / "roadmap.json",
        Path(r"C:\AI_VAULT\tmp_agent\state\brain_roadmap_actualizado_20260309.json"),
    ]
    chosen = None
    data = None
    for c in candidates:
        data = _read_json(c)
        if data is not None:
            chosen = c
            break

    current_truth = (data or {}).get("current_truth") or {}
    active_item = current_truth.get("active_item") or {}
    work_items = _extract_work_items(data)

    if not active_item and work_items:
        for wi in work_items:
            if wi.get("status_norm") == "in_progress":
                active_item = wi
                break

    counts = {
        "pending": sum(1 for x in work_items if x.get("status_norm") == "pending"),
        "in_progress": sum(1 for x in work_items if x.get("status_norm") == "in_progress"),
        "done": sum(1 for x in work_items if x.get("status_norm") == "done"),
        "blocked": sum(1 for x in work_items if x.get("status_norm") == "blocked"),
        "error": sum(1 for x in work_items if x.get("status_norm") == "error"),
    }

    return {
        "ok": True,
        "source_path": str(chosen) if chosen else None,
        "program_id": (data or {}).get("program_id"),
        "active_roadmap": (data or {}).get("active_roadmap") or (data or {}).get("roadmap_id"),
        "status": (data or {}).get("status"),
        "objective": (data or {}).get("objective"),
        "active_item": active_item,
        "work_items": work_items,
        "counts": counts,
        "raw": data,
    }


def _list_artifacts(room_id: str, limit: int = 120) -> list[dict[str, Any]]:
    room = _room_dir(room_id)
    if not room.exists():
        return []

    items: list[dict[str, Any]] = []
    for path in room.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            rel = str(path.relative_to(room)).replace("/", "\\")
            items.append({
                "name": path.name,
                "rel_path": rel,
                "abs_path": str(path),
                "kind": path.suffix.lower().lstrip(".") or "file",
                "size": stat.st_size,
                "updated_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "previewable": path.suffix.lower() in {".json", ".txt", ".md", ".log", ".ndjson", ".ps1", ".py", ".csv"},
            })
        except Exception:
            continue

    items.sort(key=lambda x: x["updated_utc"], reverse=True)
    return items[:limit]


def _runtime_payload(room_id: str) -> dict[str, Any]:
    room = _room_dir(room_id)
    snap = _read_json(room / "runtime_snapshot.json")
    return {
        "ok": True,
        "room_id": room_id,
        "bound": snap is not None,
        "runtime_snapshot": snap,
        "reason": None if snap is not None else "runtime_snapshot_missing",
    }


def _safe_rel(rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute():
        raise HTTPException(status_code=400, detail="absolute path not allowed")
    if any(part == ".." for part in rel.parts):
        raise HTTPException(status_code=400, detail="parent traversal not allowed")
    return rel


async def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, headers=headers or {})
            r.raise_for_status()
            return {"ok": True, "status_code": r.status_code, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": None}


async def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json=payload, headers=headers or {})
            try:
                content = r.json()
            except Exception:
                content = {"raw": r.text}
            return {"ok": r.is_success, "status_code": r.status_code, "data": content}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": None}


async def _advisor_health(headers: dict[str, str]) -> dict[str, Any]:
    for url in (f"{ADVISOR_BASE}/healthz", f"{ADVISOR_BASE}/v1/healthz"):
        out = await _get_json(url, headers=headers)
        if out.get("ok"):
            return out
    return out


async def _health_summary_payload(room_id: str) -> dict[str, Any]:
    headers = {"x-room-id": room_id}
    brain = await _get_json(f"{BRAIN_BASE}/v1/agent/healthz", headers=headers)
    advisor = await _advisor_health(headers)
    runtime = _runtime_payload(room_id)
    return {
        "ok": True,
        "room_id": room_id,
        "brain_8010": brain,
        "advisor_8030": advisor,
        "snapshot": {
            "ok": runtime.get("bound", False),
            "reason": runtime.get("reason"),
        },
        "summary": {
            "brain_ok": bool((brain.get("data") or {}).get("ok")) if brain.get("ok") else False,
            "advisor_ok": bool((advisor.get("data") or {}).get("ok")) if advisor.get("ok") else False,
            "runtime_bound": bool(runtime.get("bound")),
        },
        "ui_mode": "canonical_8010",
    }


def _build_process_overview(
    room_id: str,
    status_payload: dict[str, Any],
    health_payload: dict[str, Any],
    contract_payload: dict[str, Any],
    roadmap_payload: dict[str, Any],
    artifacts_count: int,
) -> dict[str, Any]:
    status = (status_payload or {}).get("data") or {}
    plan_summary = status.get("plan_summary") or {}
    plan_status = _normalize_status(plan_summary.get("status"))
    blocked = status.get("blocked") or {}
    active_step_id = status.get("active_step_id") or status.get("current_step_id") or plan_summary.get("current_step_id")
    brain_ok = bool((health_payload.get("summary") or {}).get("brain_ok"))
    advisor_ok = bool((health_payload.get("summary") or {}).get("advisor_ok"))
    runtime_bound = bool((health_payload.get("summary") or {}).get("runtime_bound"))
    contract_bound = bool(contract_payload.get("bound"))
    active_item = roadmap_payload.get("active_item") or {}
    work_counts = roadmap_payload.get("counts") or {}

    if blocked:
        current_stage = "approval_gate"
    elif plan_status == "in_progress":
        current_stage = "execution"
    elif plan_status == "done":
        current_stage = "response"
    elif contract_bound and advisor_ok:
        current_stage = "planning"
    else:
        current_stage = "intake"

    human_action_required = "apply_or_reject_required" if blocked else "monitor_only"

    stages = [
        {
            "id": "intake",
            "label": "1. Entrada / intención del usuario",
            "owner": "Humano + UI",
            "status": "done" if brain_ok else "error",
            "detail": "La solicitud entra por UI y se enruta al control plane.",
        },
        {
            "id": "contract",
            "label": "2. Contrato conversacional / interpretación",
            "owner": "Brain 8010",
            "status": "done" if contract_bound else "pending",
            "detail": "El backend aplica reglas de conversación, aclaración y formato de respuesta.",
        },
        {
            "id": "planning",
            "label": "3. Planificación / advisor",
            "owner": "Advisor 8030",
            "status": "done" if (advisor_ok and plan_status in {"in_progress", "done", "blocked"}) else ("in_progress" if advisor_ok else "pending"),
            "detail": "El advisor decide siguiente paso o publica plan para ejecución.",
        },
        {
            "id": "plan_publish",
            "label": "4. Publicación del plan",
            "owner": "Brain 8010",
            "status": "done" if plan_summary else "pending",
            "detail": "El plan pasa al store/room y queda visible para ejecución y seguimiento.",
        },
        {
            "id": "execution",
            "label": "5. Ejecución de pasos / tools",
            "owner": "Brain 8010 + tools",
            "status": "blocked" if blocked else ("in_progress" if plan_status == "in_progress" else ("done" if plan_status == "done" else "pending")),
            "detail": "Se ejecutan pasos del roadmap o del plan operativo.",
        },
        {
            "id": "approval_gate",
            "label": "6. Gate de aprobación humana",
            "owner": "Humano supervisor",
            "status": "blocked" if blocked else ("done" if plan_status in {"in_progress", "done"} else "pending"),
            "detail": "Si aparece proposal/apply, aquí interviene el humano con Apply/Reject.",
        },
        {
            "id": "artifact_persistence",
            "label": "7. Persistencia de artifacts / evidencia",
            "owner": "Brain 8010 + state",
            "status": "done" if (artifacts_count > 0 or runtime_bound) else "pending",
            "detail": "Se guardan artifacts, snapshots, audit y evidencia.",
        },
        {
            "id": "response",
            "label": "8. Presentación de respuesta",
            "owner": "UI Dashboard",
            "status": "done" if (plan_status == "done" or runtime_bound) else ("in_progress" if brain_ok else "pending"),
            "detail": "La UI presenta estado, artifacts, respuesta y trazabilidad.",
        },
        {
            "id": "error_correction",
            "label": "9. Error -> corrección -> reintento",
            "owner": "Brain + advisor + humano",
            "status": "in_progress" if (not brain_ok or not advisor_ok or plan_status == "error") else "pending",
            "detail": "Si algo falla, se diagnostica, corrige y se vuelve a intentar.",
        },
    ]

    for stage in stages:
        if stage["id"] == current_stage and stage["status"] == "pending":
            stage["status"] = "in_progress"

    actors = [
        {
            "name": "Humano supervisor",
            "role": "Define objetivos, supervisa y aprueba/rechaza cuando existe bloqueo.",
            "when_intervenes": "Inicio, approvals y correcciones estratégicas.",
            "current_state": "approval_required" if blocked else "monitoring",
        },
        {
            "name": "Dashboard UI (8010/ui)",
            "role": "Visualiza estado real, artifacts, timeline, flujo y roadmap.",
            "when_intervenes": "Siempre, como consola operativa.",
            "current_state": "live" if brain_ok else "degraded",
        },
        {
            "name": "Brain Server 8010",
            "role": "Control plane, SSOT, estado por room, ejecución, snapshots, apply/reject.",
            "when_intervenes": "Siempre.",
            "current_state": "healthy" if brain_ok else "error",
        },
        {
            "name": "Advisor 8030",
            "role": "Planner/advisor para decidir próximos pasos o publicar plan.",
            "when_intervenes": "Cuando hay planning, re-planning o explicación de ruta.",
            "current_state": "healthy" if advisor_ok else "degraded",
        },
        {
            "name": "Tools / runtime / filesystem",
            "role": "Ejecutan acciones y materializan artifacts/evidencias.",
            "when_intervenes": "Durante la ejecución.",
            "current_state": "active" if plan_status in {"in_progress", "done"} else "idle",
        },
        {
            "name": "Roadmap engine",
            "role": "Marca el item activo, etapas y progreso del autodesarrollo.",
            "when_intervenes": "Cuando el trabajo cae sobre work items del roadmap.",
            "current_state": str(active_item.get("status") or active_item.get("status_norm") or "unknown"),
        },
    ]

    summary_text = (
        "Flujo operativo: usuario/supervisor -> UI dashboard -> brain_server(8010) -> "
        "contrato/politicas -> advisor/planner(8030) si hace falta -> publicacion de plan -> "
        "ejecucion de pasos y tools -> approval gate humano si aparece bloqueo -> "
        "persistencia de artifacts/evidencia -> respuesta visible en UI -> "
        "si hay fallo, entra el loop de error/correccion/reintento."
    )

    return {
        "ok": True,
        "room_id": room_id,
        "current_stage": current_stage,
        "current_stage_label": next((x["label"] for x in stages if x["id"] == current_stage), current_stage),
        "active_step_id": active_step_id,
        "plan_status": plan_status,
        "human_action_required": human_action_required,
        "active_roadmap_item": active_item,
        "roadmap_counts": work_counts,
        "summary_text": summary_text,
        "actors": actors,
        "stages": stages,
    }


@router.get("/ui", include_in_schema=False)
def ui_index() -> FileResponse:
    return FileResponse(UI_ROOT / "index.html")


@router.get("/ui/", include_in_schema=False)
def ui_index_slash() -> FileResponse:
    return FileResponse(UI_ROOT / "index.html")


@router.get("/ui/api/bootstrap")
async def ui_bootstrap(room_id: str = Query(...)) -> JSONResponse:
    ts0 = time.time()
    headers = {"x-room-id": room_id}

    status = await _get_json(f"{BRAIN_BASE}/v1/agent/status?room_id={room_id}", headers=headers)
    health = await _health_summary_payload(room_id)
    contract = _contract_payload()
    roadmap = _roadmap_payload()
    runtime = _runtime_payload(room_id)
    artifacts = _list_artifacts(room_id, limit=60)

    room = _room_dir(room_id)
    evidence = {
        "audit_tail": _tail_lines(room / "audit.ndjson", 80),
        "episode_tail": _tail_lines(room / "episode.json", 20),
    }

    process_overview = _build_process_overview(
        room_id=room_id,
        status_payload=status,
        health_payload=health,
        contract_payload=contract,
        roadmap_payload=roadmap,
        artifacts_count=len(artifacts),
    )

    elapsed_ms = int((time.time() - ts0) * 1000)
    return JSONResponse({
        "ok": True,
        "ts": _now_iso(),
        "elapsed_ms": elapsed_ms,
        "room_id": room_id,
        "staleness": {
            "is_live": elapsed_ms < 5000,
            "age_ms": elapsed_ms,
            "max_fresh_ms": 5000,
        },
        "status": status,
        "health": health,
        "contract": contract,
        "roadmap": roadmap,
        "conversation_runtime_v2": runtime,
        "process_overview": process_overview,
        "artifacts": {
            "recent": artifacts[:20],
            "count": len(artifacts),
        },
        "evidence": evidence,
    })


@router.get("/ui/api/process/overview")
async def ui_process_overview(room_id: str = Query(...)) -> JSONResponse:
    headers = {"x-room-id": room_id}
    status = await _get_json(f"{BRAIN_BASE}/v1/agent/status?room_id={room_id}", headers=headers)
    health = await _health_summary_payload(room_id)
    contract = _contract_payload()
    roadmap = _roadmap_payload()
    artifacts = _list_artifacts(room_id, limit=60)
    payload = _build_process_overview(
        room_id=room_id,
        status_payload=status,
        health_payload=health,
        contract_payload=contract,
        roadmap_payload=roadmap,
        artifacts_count=len(artifacts),
    )
    return JSONResponse(payload)


@router.get("/ui/api/room/status")
async def ui_room_status(room_id: str = Query(...)) -> JSONResponse:
    headers = {"x-room-id": room_id}
    data = await _get_json(f"{BRAIN_BASE}/v1/agent/status?room_id={room_id}", headers=headers)
    return JSONResponse(data)


@router.get("/ui/api/health/summary")
async def ui_health_summary(room_id: str = Query(...)) -> JSONResponse:
    return JSONResponse(await _health_summary_payload(room_id))


@router.get("/ui/api/roadmap/active")
async def ui_roadmap_active() -> JSONResponse:
    return JSONResponse(_roadmap_payload())


@router.get("/ui/api/conversation/contract_v2")
async def ui_contract_v2() -> JSONResponse:
    return JSONResponse(_contract_payload())


@router.get("/ui/api/conversation/runtime_status_v2")
async def ui_runtime_status_v2(room_id: str = Query(...)) -> JSONResponse:
    return JSONResponse(_runtime_payload(room_id))


@router.get("/ui/api/artifacts")
async def ui_artifacts(room_id: str = Query(...), limit: int = Query(120, ge=1, le=500)) -> JSONResponse:
    items = _list_artifacts(room_id, limit=limit)
    return JSONResponse({"ok": True, "room_id": room_id, "items": items})


@router.get("/ui/api/artifact/preview")
async def ui_artifact_preview(room_id: str = Query(...), rel_path: str = Query(...)) -> PlainTextResponse:
    room = _room_dir(room_id)
    safe_rel = _safe_rel(rel_path)
    target = room / safe_rel
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return PlainTextResponse(_read_text(target))


@router.get("/ui/api/evidence")
async def ui_evidence(room_id: str = Query(...), limit: int = Query(80, ge=1, le=500)) -> JSONResponse:
    room = _room_dir(room_id)
    events = _tail_lines(room / "audit.ndjson", max_lines=limit)
    return JSONResponse({"ok": True, "room_id": room_id, "events": events})


@router.post("/ui/api/apply")
async def ui_apply(request: Request) -> JSONResponse:
    body = await request.json()
    room_id = body.get("room_id") or request.headers.get("x-room-id") or "default"
    headers = {"x-room-id": room_id}
    result = await _post_json(f"{BRAIN_BASE}/v1/agent/apply", body, headers=headers)
    return JSONResponse(status_code=result.get("status_code") or 500, content=result)


@router.post("/ui/api/reject")
async def ui_reject(request: Request) -> JSONResponse:
    body = await request.json()
    room_id = body.get("room_id") or request.headers.get("x-room-id") or "default"
    headers = {"x-room-id": room_id}
    if "reason" not in body:
        body["reason"] = "ui_reject"
    result = await _post_json(f"{BRAIN_BASE}/v1/agent/reject", body, headers=headers)
    return JSONResponse(status_code=result.get("status_code") or 500, content=result)


@router.post("/ui/api/run_once")
async def ui_run_once(request: Request) -> JSONResponse:
    body = await request.json()
    room_id = body.get("room_id") or request.headers.get("x-room-id") or "default"
    headers = {"x-room-id": room_id}
    result = await _post_json(f"{BRAIN_BASE}/v1/agent/run_once", body, headers=headers)
    return JSONResponse(status_code=result.get("status_code") or 500, content=result)


@router.post("/ui/api/advisor/next")
async def ui_advisor_next(request: Request) -> JSONResponse:
    body = await request.json()
    room_id = body.get("room_id") or request.headers.get("x-room-id") or "default"
    headers = {"x-room-id": room_id}
    result = await _post_json(f"{ADVISOR_BASE}/v1/advisor/next", body, headers=headers)
    return JSONResponse(status_code=result.get("status_code") or 500, content=result)


def setup_dashboard(app: FastAPI) -> None:
    if getattr(app.state, "dashboard_vnext_mounted", False):
        return

    mounted_names = {getattr(r, "name", None) for r in app.routes}
    if "brain_dashboard_assets" not in mounted_names:
        app.mount("/ui/assets", StaticFiles(directory=str(UI_ROOT)), name="brain_dashboard_assets")

    app.include_router(router)
    app.state.dashboard_vnext_mounted = True