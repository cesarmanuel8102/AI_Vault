from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_ndjson(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


@dataclass
class AgentPaths:
    root: Path
    state_dir: Path
    mission_path: Path
    plan_path: Path
    log_ndjson: Path

    @staticmethod
    def default(root: Optional[str] = None, room_id: Optional[str] = None) -> "AgentPaths":
        r = Path(root or r"C:\AI_VAULT\00_identity").resolve()
        rid = (room_id or "default").strip() or "default"
        st = (Path(r"C:\AI_VAULT\state\agent") / rid).resolve()  # per-room persisted agent state
        return AgentPaths(
            root=r,
            state_dir=st,
            mission_path=st / "mission.json",
            plan_path=st / "plan.json",
            log_ndjson=Path(r"C:\AI_VAULT\logs\agent_events.ndjson"),
        )


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: Optional[str] = None


ToolDispatcher = Callable[[str, Dict[str, Any]], ToolResult]


class AgentLoop:
    def __init__(self, paths: Optional[AgentPaths] = None, dispatch_tool: Optional[ToolDispatcher] = None):
        self.paths = paths or AgentPaths.default()
        # ensure persistent dirs exist
        try:
            self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            self.paths.log_ndjson.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.dispatch_tool = dispatch_tool

    def load_mission(self) -> Dict[str, Any]:
        return _read_json(self.paths.mission_path, {
            "mission_id": None,
            "created_ts": None,
            "updated_ts": None,
            "goal": None,
            "status": "idle",
            "notes": [],
        })

    def load_plan(self) -> Dict[str, Any]:
        return _read_json(self.paths.plan_path, {
            "mission_id": None,
            "created_ts": None,
            "updated_ts": None,
            "profile": "default",
            "cursor": 0,
            "steps": [],
        })

    def save_mission(self, mission: Dict[str, Any]) -> None:
        mission["updated_ts"] = utc_iso()
        _write_json(self.paths.mission_path, mission)

    def save_plan(self, plan: Dict[str, Any]) -> None:
        plan["updated_ts"] = utc_iso()
        _write_json(self.paths.plan_path, plan)

    def log_event(self, kind: str, payload: Dict[str, Any]) -> None:
        _append_ndjson(self.paths.log_ndjson, {"ts": utc_iso(), "kind": kind, **payload})

    def plan(self, goal: str, profile: str = "default", force_new: bool = False) -> Dict[str, Any]:
        mission = self.load_mission()
        plan = self.load_plan()

        if force_new or not mission.get("mission_id"):
            mission_id = f"mission_{uuid.uuid4().hex[:12]}"
            mission = {
                "mission_id": mission_id,
                "created_ts": utc_iso(),
                "updated_ts": utc_iso(),
                "goal": goal,
                "status": "planned",
                "notes": [],
            }
            plan = {
                "mission_id": mission_id,
                "created_ts": utc_iso(),
                "updated_ts": utc_iso(),
                "profile": profile,
                "cursor": 0,
                "steps": self._default_plan_steps(goal),
            }
        else:
            mission["goal"] = goal
            mission["status"] = mission.get("status") or "planned"
            plan["profile"] = profile or plan.get("profile") or "default"
            if not plan.get("steps"):
                plan["steps"] = self._default_plan_steps(goal)

        self.save_mission(mission)
        self.save_plan(plan)
        self.log_event("plan_created", {"mission_id": mission["mission_id"], "profile": plan["profile"], "steps": len(plan["steps"])})
        return {"ok": True, "mission": mission, "plan": plan}

    def _default_plan_steps(self, goal: str) -> List[Dict[str, Any]]:
        return [
            {"id": "s1", "title": "Inspeccionar estado actual", "status": "pending", "tool_calls": [
                {"tool": "list_dir", "args": {"path": r"C:\AI_VAULT\00_identity"}},
                {"tool": "list_dir", "args": {"path": r"C:\AI_VAULT\tmp_agent"}},
            ], "result": None, "error": None},
            {"id": "s2", "title": "Validar archivos críticos", "status": "pending", "tool_calls": [
                {"tool": "read_file", "args": {"path": r"C:\AI_VAULT\tmp_agent\dev_loop.py"}},
                {"tool": "read_file", "args": {"path": r"C:\AI_VAULT\tmp_agent\smoke_runner.py"}},
            ], "result": None, "error": None},
            {"id": "s3", "title": "Checkpoint", "status": "pending", "tool_calls": [
                {"tool": "append_file", "args": {"path": r"C:\AI_VAULT\logs\agent_checkpoints.ndjson", "text": json.dumps({"ts": utc_iso(), "goal": goal}) + "\n"}},
            ], "result": None, "error": None},
        ]

    def step(self) -> Dict[str, Any]:
        mission = self.load_mission()
        plan = self.load_plan()

        if not mission.get("mission_id") or plan.get("mission_id") != mission.get("mission_id"):
            return {"ok": False, "error": "NO_ACTIVE_MISSION"}

        steps = plan.get("steps") or []
        cursor = int(plan.get("cursor") or 0)

        while cursor < len(steps) and steps[cursor].get("status") in ("done", "skipped"):
            cursor += 1
        plan["cursor"] = cursor

        if cursor >= len(steps):
            mission["status"] = "done"
            self.save_mission(mission)
            self.save_plan(plan)
            self.log_event("mission_done", {"mission_id": mission["mission_id"]})
            return {"ok": True, "mission": mission, "plan": plan, "note": "NO_MORE_STEPS"}

        step_obj = steps[cursor]
        if step_obj.get("status") not in ("pending", "failed"):
            step_obj["status"] = "pending"

        mission["status"] = "running"
        self.save_mission(mission)

        if not self.dispatch_tool:
            step_obj["status"] = "blocked"
            step_obj["error"] = "NO_TOOL_DISPATCHER_CONFIGURED"
            steps[cursor] = step_obj
            plan["steps"] = steps
            self.save_plan(plan)
            self.log_event("step_blocked", {"mission_id": mission["mission_id"], "step_id": step_obj.get("id"), "error": step_obj["error"]})
            return {"ok": False, "mission": mission, "plan": plan, "step": step_obj}

        outputs: List[Dict[str, Any]] = []
        for call in (step_obj.get("tool_calls") or []):
            tool = str(call.get("tool"))
            args = call.get("args") or {}
            # ARGS_COMPAT_CONTENT_TO_TEXT_PATCH: compatibilidad planner -> tools
            if isinstance(args, dict) and ("content" in args) and ("text" not in args) and tool in ("write_file", "append_file"):
                args["text"] = args.get("content")
                try:
                    del args["content"]
                except Exception:
                    pass
            # RUNTIME_SUMMARY_AUTOFILL_S2_PATCH: si write_file apunta a docs\\summary_*.md, resumir SIEMPRE desde step s2 (read_file ok); fallback = último read_file ok
            try:
                if tool == "write_file" and isinstance(args, dict):
                    pth = str(args.get("path") or "")
                    if ("\\docs\\summary_" in pth.lower()) and pth.lower().endswith(".md"):
                        src_text = None
                        # 1) Preferencia estricta: step id == 's2' y su read_file ok
                        try:
                            for _st in (plan.get("steps") or []):
                                if not isinstance(_st, dict):
                                    continue
                                if str(_st.get("id") or "") != "s2":
                                    continue
                                for _res in (_st.get("result") or []):
                                    if not isinstance(_res, dict):
                                        continue
                                    if str(_res.get("tool") or "") != "read_file":
                                        continue
                                    if not bool(_res.get("ok", False)):
                                        continue
                                    out = _res.get("output") or {}
                                    if isinstance(out, dict):
                                        t = out.get("text")
                                        if isinstance(t, str) and t.strip():
                                            src_text = t
                                            break
                                break
                        except Exception:
                            src_text = None
            
                        # 2) Fallback: último read_file ok (por robustez)
                        if not (isinstance(src_text, str) and src_text.strip()):
                            try:
                                for _st in reversed(plan.get("steps") or []):
                                    if not isinstance(_st, dict):
                                        continue
                                    for _res in (_st.get("result") or []):
                                        if not isinstance(_res, dict):
                                            continue
                                        if str(_res.get("tool") or "") != "read_file":
                                            continue
                                        if not bool(_res.get("ok", False)):
                                            continue
                                        out = _res.get("output") or {}
                                        if isinstance(out, dict):
                                            t = out.get("text")
                                            if isinstance(t, str) and t.strip():
                                                src_text = t
                                                break
                                    if src_text:
                                        break
                            except Exception:
                                src_text = None
            
                        # 3) resumen local simple (hasta 8 bullets)
                        if isinstance(src_text, str) and src_text.strip():
                            _lines = [ln.strip() for ln in src_text.replace("\r\n","\n").split("\n") if ln.strip()]
                            bullets = []
                            for ln in _lines:
                                ln2 = ln if len(ln) <= 180 else (ln[:177] + "...")
                                bullets.append("- " + ln2)
                                if len(bullets) >= 8:
                                    break
                            if not bullets:
                                bullets = ["- (sin contenido para resumir)"]
                            summary = "\n".join(bullets)
                            # escribir al destino; el compat content->text también lo cubrirá
                            args["text"] = summary
                            if "content" in args and isinstance(args.get("content"), str):
                                args["content"] = summary
            except Exception:
                pass
            # SUMMARY_TS_NORMALIZE_PLACEHOLDER_PATCH: normaliza docs\\summary_<ts>.md (placeholder invalido en Windows) -> docs\\summary_<epoch>.md
            try:
                if tool == "write_file" and isinstance(args, dict):
                    pth = str(args.get("path") or "")
                    if "\\docs\\summary_" in pth.lower() and pth.lower().endswith(".md"):
                        now_epoch = int(__import__('time').time())
                        import re as _re
                        # Caso 1: summary_<ts>.md literal
                        pth2 = _re.sub(r'(?i)\\docs\\summary_<ts>\\.md$', r'\\docs\\summary_%d.md' % now_epoch, pth)
                        # Caso 2: cualquier summary_ALGO.md (incluye placeholders raros)
                        if pth2 == pth:
                            pth2 = _re.sub(r'(?i)\\docs\\summary_[^\\\\]+\\.md$', r'\\docs\\summary_%d.md' % now_epoch, pth)
                        args["path"] = pth2
            except Exception:
                pass
            r = self.dispatch_tool(tool, args)

            outputs.append({"tool": tool, "ok": r.ok, "output": r.output, "error": r.error})
            if not r.ok:
                step_obj["status"] = "failed"
                step_obj["error"] = r.error or "TOOL_FAILED"
                step_obj["result"] = outputs
                steps[cursor] = step_obj
                plan["steps"] = steps
                self.save_plan(plan)
                self.log_event("step_failed", {"mission_id": mission["mission_id"], "step_id": step_obj.get("id"), "tool": tool, "error": step_obj["error"]})
                return {"ok": False, "mission": mission, "plan": plan, "step": step_obj}

        step_obj["status"] = "done"
        step_obj["result"] = outputs
        step_obj["error"] = None
        steps[cursor] = step_obj
        plan["steps"] = steps
        plan["cursor"] = cursor + 1
        self.save_plan(plan)

        self.log_event("step_done", {"mission_id": mission["mission_id"], "step_id": step_obj.get("id")})
        return {"ok": True, "mission": mission, "plan": plan, "step": step_obj}

    def eval(self) -> Dict[str, Any]:
        mission = self.load_mission()
        plan = self.load_plan()
        if not mission.get("mission_id"):
            return {"ok": False, "error": "NO_ACTIVE_MISSION"}

        steps = plan.get("steps") or []
        done = sum(1 for s in steps if s.get("status") == "done")
        failed = sum(1 for s in steps if s.get("status") == "failed")
        pending = sum(1 for s in steps if s.get("status") == "pending")
        blocked = sum(1 for s in steps if s.get("status") == "blocked")

        verdict = "continue"
        if blocked > 0:
            verdict = "blocked"
            mission["status"] = "blocked"
        elif pending == 0 and failed == 0:
            verdict = "done"
            mission["status"] = "done"

        self.save_mission(mission)
        self.log_event("eval", {"mission_id": mission["mission_id"], "verdict": verdict, "done": done, "failed": failed, "pending": pending, "blocked": blocked})

        return {"ok": True, "mission": mission, "stats": {"done": done, "failed": failed, "pending": pending, "blocked": blocked}, "verdict": verdict}

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "mission": self.load_mission(), "plan": self.load_plan()}

    def reset(self) -> Dict[str, Any]:
        _write_json(self.paths.mission_path, {"mission_id": None, "created_ts": None, "updated_ts": utc_iso(), "goal": None, "status": "idle", "notes": []})
        _write_json(self.paths.plan_path, {"mission_id": None, "created_ts": None, "updated_ts": utc_iso(), "profile": "default", "cursor": 0, "steps": []})
        self.log_event("reset", {})
        return {"ok": True}




