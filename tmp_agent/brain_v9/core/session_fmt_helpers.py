"""
brain_v9.core.session_fmt_helpers
=================================

B7-STRANGLER-06: Pure, side-effect-free tool-result formatters extracted from
BrainSession's ``_fmt_*`` classmethod bundle (formerly in
``tmp_agent/brain_v9/core/session.py`` @ lines 4447-4774).

Each formatter takes the raw dict (or list, where applicable) returned by a
brain tool and produces a human-readable Spanish single- or multi-line string
suitable for chat-area display.

Contract
--------
* Module-level pure functions ``fmt_<tool_name>(out) -> str``.
* No imports from ``brain_v9.core.session`` (no circular dependency).
* No I/O, no network, no config, no logging.
* Behaviour is byte-identical to the prior classmethods.

BrainSession keeps the ``_fmt_<name>`` classmethods as one-line shims that
delegate here, preserving:

* ``BrainSession._format_tool_result``'s ``getattr(cls, method_name)`` lookup,
* the public ``_TOOL_FORMATTERS`` registry (incl. ``check_url`` alias),
* and any external code paths that bind to the classmethod descriptor.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

__all__ = [
    "format_action_value",
    "format_tool_result",
    "fmt_check_port",
    "fmt_check_http_service",
    "fmt_check_all_services",
    "fmt_check_service_status",
    "fmt_get_live_autonomy_status",
    "fmt_run_diagnostic",
    "fmt_get_system_info",
    "fmt_run_command",
    "fmt_read_file",
    "fmt_list_directory",
    "fmt_search_files",
    "fmt_list_processes",
    "fmt_grep_codebase",
    "fmt_list_recent_brain_changes",
    "fmt_get_chat_metrics",
    "fmt_semantic_memory_search",
    "fmt_get_technical_introspection",
]


def format_action_value(value: Any) -> str:
    """Format an action value (bool/int/float/str/list/dict) for compact display.

    Pure function extracted from BrainSession._format_action_value.
    Recursively calls itself for dict values.
    """
    if isinstance(value, bool):
        return "si" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        compact = ", ".join(str(item) for item in value[:4])
        if len(value) > 4:
            compact += f" (+{len(value)-4} mas)"
        return compact or "(vacio)"
    if isinstance(value, dict):
        pairs = []
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)):
                pairs.append(f"{key}={format_action_value(item)}")
            if len(pairs) >= 4:
                break
        return ", ".join(pairs) if pairs else json.dumps(value, ensure_ascii=False)[:160]
    return str(value)


def fmt_check_port(out: Dict) -> str:
    port = out.get("port", "?")
    status = out.get("status", "desconocido")
    if status == "libre":
        return f"Puerto {port} — libre, ningun proceso escuchando"
    procs = out.get("processes", [])
    # Deduplicate by PID, skip PID 0 (kernel/idle) and noisy entries
    seen = {}
    for p in procs:
        pid = p.get("pid", "?")
        name = p.get("name", "").strip()
        # Skip PID 0 (kernel TIME_WAIT), empty names, and error messages
        if pid in ("0", 0) or not name or "No tasks are running" in name:
            continue
        if pid not in seen:
            state = p.get("state", "")
            seen[pid] = (name, state)
    if seen:
        parts = []
        for pid, (name, state) in list(seen.items())[:4]:
            s = f"{name} (PID {pid})"
            if state and state != "LISTENING":
                s += f" [{state}]"
            parts.append(s)
        return f"Puerto {port} — activo: {', '.join(parts)}"
    # All procs were filtered — port is in use but only by kernel
    return f"Puerto {port} — en uso (conexiones residuales del kernel)"


def fmt_check_http_service(out: Dict) -> str:
    url = out.get("url", "?")
    code = out.get("status_code", "?")
    healthy = out.get("is_healthy", False)
    err = out.get("error")
    # Shorten URL for display
    short = url.replace("http://localhost:", ":").replace("http://127.0.0.1:", ":")
    if err:
        return f"{short} — error: {err}"
    status = "saludable" if healthy else "respondiendo"
    return f"{short} — {code} OK, {status}" if code == 200 else f"{short} — codigo {code}"


def fmt_check_all_services(out: Dict) -> str:
    overall = out.get("overall_status", "desconocido")
    services = out.get("services", [])
    if not services:
        return f"Servicios: {overall}"
    parts = []
    for svc in services:
        name = svc.get("name", "?")
        port = svc.get("port", "?")
        running = svc.get("running", False)
        icon = "OK" if running else "CAIDO"
        parts.append(f"  {name} (:{port}) — {icon}")
    header = "Todos los servicios operativos" if overall == "healthy" else f"Estado general: {overall}"
    return header + "\n" + "\n".join(parts)


def fmt_check_service_status(out: Dict) -> str:
    checked = out.get("services_checked", 0)
    services = out.get("services", [])
    if isinstance(services, list) and services:
        parts = []
        for svc in services:
            if isinstance(svc, dict):
                name = svc.get("name", "?")
                running = svc.get("running", svc.get("status") == "running")
                parts.append(f"{name}: {'OK' if running else 'CAIDO'}")
        if parts:
            return ", ".join(parts)
    return f"{checked} servicios verificados"


def fmt_get_live_autonomy_status(out: Dict) -> str:
    health = out.get("brain_health") or {}
    strategy = out.get("strategy_summary") or {}
    utility = out.get("utility") or {}
    next_a = out.get("next_actions") or {}
    parts = []
    if health:
        parts.append(f"Brain: {health.get('status', 'desconocido')}, sessions={health.get('sessions', '?')}")
    u = utility.get("u_score", utility.get("U", "N/A"))
    verdict = utility.get("verdict", next_a.get("verdict", "N/A"))
    parts.append(f"Utility U={u}, veredicto={verdict}")
    top = next_a.get("top_action") or strategy.get("top_action")
    if top:
        parts.append(f"Accion prioritaria: {top}")
    blockers = next_a.get("blockers", [])
    if blockers:
        parts.append(f"Blockers: {', '.join(blockers[:4])}")
    return "\n".join(parts)


def fmt_run_diagnostic(out: Dict) -> str:
    summary = out.get("summary") or {}
    total = summary.get("total_checks", 0)
    ok = summary.get("successful", 0)
    status = summary.get("status", "desconocido")
    checks = (out.get("diagnostic") or {}).get("checks", [])
    parts = [f"Diagnostico: {ok}/{total} checks OK — {status}"]
    for c in checks[:5]:
        name = c.get("name", "?")
        result = c.get("result", {})
        success = result.get("success", False)
        parts.append(f"  {name}: {'OK' if success else 'FALLO'}")
    return "\n".join(parts)


def fmt_get_system_info(out: Dict) -> str:
    cpu = out.get("cpu_percent", "?")
    mem = out.get("memory", {})
    disk = out.get("disk", {})
    parts = [f"CPU: {cpu}%"]
    if mem:
        total = mem.get("total_gb", "?")
        avail = mem.get("available_gb", "?")
        parts.append(f"RAM: {avail}GB libres de {total}GB")
    if disk:
        free = disk.get("free_gb", "?")
        total_d = disk.get("total_gb", "?")
        parts.append(f"Disco C: {free}GB libres de {total_d}GB")
    return " | ".join(parts)


def fmt_run_command(out: Dict) -> str:
    stdout = out.get("stdout", "")
    stderr = out.get("stderr", "")
    code = out.get("return_code", out.get("exit_code", "?"))
    result = stdout.strip() if stdout else stderr.strip()
    if not result:
        return f"Comando ejecutado (codigo {code}), sin salida"
    # Truncate long output
    if len(result) > 500:
        result = result[:497] + "..."
    return result


def fmt_read_file(out: Dict) -> str:
    path = out.get("path", "?")
    content = out.get("content", "")
    lines = out.get("lines", 0) or (content.count("\n") + 1 if content else 0)
    short_path = path.replace("C:\\AI_VAULT\\", "").replace("C:/AI_VAULT/", "")
    if content and len(content) > 300:
        return f"{short_path} ({lines} lineas)\n{content[:300]}..."
    return f"{short_path} ({lines} lineas)" + (f"\n{content}" if content else "")


def fmt_list_directory(out: Any) -> str:
    # Handle both list (direct file list) and dict (structured response)
    if isinstance(out, list):
        if len(out) <= 15:
            return ", ".join(str(x) for x in out)
        return f"{len(out)} archivos: {', '.join(str(x) for x in out[:10])}..."
    if isinstance(out, dict):
        path = out.get("path", "?")
        items = out.get("items", out.get("entries", []))
        if isinstance(items, list):
            if len(items) <= 15:
                return f"{path}: {', '.join(str(x) for x in items)}"
            return f"{path}: {len(items)} elementos"
        return f"{path}: {items}"
    return str(out)[:300]


def fmt_search_files(out: Dict) -> str:
    matches = out.get("matches", out.get("results", []))
    if isinstance(matches, list):
        if not matches:
            return "Sin resultados"
        lines = [f"{len(matches)} archivo(s) encontrado(s):"]
        for m in matches[:8]:
            if isinstance(m, dict):
                lines.append(f"  {m.get('file', m.get('path', '?'))}")
            else:
                lines.append(f"  {m}")
        if len(matches) > 8:
            lines.append(f"  ... y {len(matches)-8} mas")
        return "\n".join(lines)
    return str(matches)[:400]


def fmt_list_processes(out: Dict) -> str:
    procs = out.get("processes", [])
    if isinstance(procs, list) and procs:
        lines = [f"{len(procs)} proceso(s):"]
        for p in procs[:10]:
            if isinstance(p, dict):
                name = p.get("name", "?")
                pid = p.get("pid", "?")
                lines.append(f"  {name} (PID {pid})")
            else:
                lines.append(f"  {p}")
        if len(procs) > 10:
            lines.append(f"  ... y {len(procs)-10} mas")
        return "\n".join(lines)
    return str(out)[:300]


def fmt_grep_codebase(out: Any) -> str:
    """grep_codebase returns a List[Dict] of {rel_path, line, text}."""
    if not isinstance(out, list):
        return str(out)[:400]
    if not out:
        return "Sin coincidencias en el codebase"
    # First entry may be {"error": "..."}
    if isinstance(out[0], dict) and "error" in out[0] and len(out) == 1:
        return f"grep_codebase: {out[0]['error']}"
    lines = [f"{len(out)} coincidencia(s):"]
    for hit in out[:8]:
        if not isinstance(hit, dict):
            continue
        rel = hit.get("rel_path") or hit.get("path", "?")
        ln = hit.get("line", "?")
        txt = (hit.get("text") or "").strip()[:120]
        lines.append(f"  {rel}:{ln} — {txt}")
    if len(out) > 8:
        lines.append(f"  ... y {len(out)-8} mas")
    return "\n".join(lines)


def fmt_list_recent_brain_changes(out: Dict) -> str:
    """list_recent_brain_changes returns ledger + edited files."""
    if not isinstance(out, dict):
        return str(out)[:400]
    ledger = out.get("ledger") or out.get("ledger_entries") or []
    edits = out.get("edited_files") or out.get("recent_edits") or []
    days = out.get("days", "?")
    parts = [f"Cambios recientes (ultimos {days}d):"]
    if isinstance(ledger, list) and ledger:
        parts.append(f"  Ledger formal: {len(ledger)} entradas")
        for e in ledger[:4]:
            if isinstance(e, dict):
                title = e.get("title") or e.get("description") or e.get("name", "?")
                when = e.get("date") or e.get("ts") or e.get("timestamp", "")
                parts.append(f"    - {str(title)[:90]} ({when})")
    if isinstance(edits, list) and edits:
        parts.append(f"  Ediciones directas: {len(edits)} archivo(s)")
        for e in edits[:6]:
            if isinstance(e, dict):
                p = e.get("path") or e.get("file", "?")
                mt = e.get("mtime") or e.get("modified", "")
                parts.append(f"    - {p} ({mt})")
            else:
                parts.append(f"    - {e}")
    if len(parts) == 1:
        return f"Sin cambios registrados en los ultimos {days} dias"
    return "\n".join(parts)


def fmt_get_chat_metrics(out: Dict) -> str:
    """get_chat_metrics returns conversations, success_rate, routes, errors."""
    if not isinstance(out, dict):
        return str(out)[:400]
    conv = out.get("conversations") or out.get("total_conversations", "?")
    sr = out.get("success_rate")
    if isinstance(sr, (int, float)):
        sr_str = f"{sr*100:.1f}%" if sr <= 1 else f"{sr:.1f}%"
    else:
        sr_str = str(sr or "?")
    parts = [f"Chats: {conv} | success_rate={sr_str}"]
    routes = out.get("routes") or {}
    if isinstance(routes, dict) and routes:
        top = sorted(routes.items(), key=lambda kv: -(kv[1] if isinstance(kv[1], int) else 0))[:4]
        parts.append("  Routes: " + ", ".join(f"{k}={v}" for k, v in top))
    errs = out.get("errors") or out.get("error_counts") or {}
    if isinstance(errs, dict) and errs:
        top_e = sorted(errs.items(), key=lambda kv: -(kv[1] if isinstance(kv[1], int) else 0))[:3]
        parts.append("  Errors: " + ", ".join(f"{k}={v}" for k, v in top_e))
    validators = out.get("validators") or {}
    if isinstance(validators, dict) and validators:
        tot = sum(v for v in validators.values() if isinstance(v, int))
        parts.append(f"  Validators fired: {tot} (en {len(validators)} categorias)")
    return "\n".join(parts)


def fmt_semantic_memory_search(out: Dict) -> str:
    """semantic_memory_search returns {results: [...], query: ...}."""
    if not isinstance(out, dict):
        return str(out)[:400]
    results = out.get("results") or out.get("matches") or []
    q = out.get("query", "")
    if not isinstance(results, list) or not results:
        return f"Memoria semantica: sin resultados para '{q}'"
    parts = [f"Memoria semantica '{q}': {len(results)} match(es)"]
    for r in results[:5]:
        if isinstance(r, dict):
            score = r.get("score") or r.get("similarity")
            txt = r.get("text") or r.get("content") or r.get("snippet", "")
            src = r.get("source") or r.get("session_id") or ""
            score_s = f"{score:.2f}" if isinstance(score, (int, float)) else "?"
            head = str(txt).strip().replace("\n", " ")[:140]
            parts.append(f"  [{score_s}] {head}" + (f" <{src}>" if src else ""))
        else:
            parts.append(f"  {str(r)[:140]}")
    if len(results) > 5:
        parts.append(f"  ... y {len(results)-5} mas")
    return "\n".join(parts)


def fmt_get_technical_introspection(out: Dict) -> str:
    """get_technical_introspection returns process/VRAM/code/capabilities snapshot."""
    if not isinstance(out, dict):
        return str(out)[:400]
    proc = out.get("process") or {}
    vram = out.get("vram") or out.get("gpu") or {}
    code = out.get("code") or out.get("codebase") or {}
    caps = out.get("capabilities") or out.get("tools") or {}
    parts = []
    if isinstance(proc, dict) and proc:
        pid = proc.get("pid", "?")
        uptime = proc.get("uptime") or proc.get("uptime_s", "?")
        mem = proc.get("memory_mb") or proc.get("rss_mb", "?")
        parts.append(f"Brain PID {pid} | uptime={uptime} | RAM={mem}MB")
    if isinstance(vram, dict) and vram:
        used = vram.get("used_mb") or vram.get("vram_used_mb", "?")
        total = vram.get("total_mb") or vram.get("vram_total_mb", "?")
        parts.append(f"GPU VRAM: {used}/{total}MB")
    if isinstance(code, dict) and code:
        files = code.get("python_files") or code.get("files", "?")
        loc = code.get("lines_of_code") or code.get("loc", "?")
        parts.append(f"Codebase: {files} archivos Python, {loc} LOC")
    if isinstance(caps, dict) and caps:
        n = caps.get("count") or caps.get("total") or len(caps)
        parts.append(f"Capacidades registradas: {n}")
    elif isinstance(caps, list):
        parts.append(f"Capacidades registradas: {len(caps)}")
    return "\n".join(parts) if parts else str(out)[:400]


# Tool formatter registry: maps tool name to formatter function in this module.
_TOOL_FORMATTER_FUNCS: Dict[str, str] = {
    "check_port": "fmt_check_port",
    "check_http_service": "fmt_check_http_service",
    "check_url": "fmt_check_http_service",
    "check_all_services": "fmt_check_all_services",
    "check_service_status": "fmt_check_service_status",
    "get_live_autonomy_status": "fmt_get_live_autonomy_status",
    "run_diagnostic": "fmt_run_diagnostic",
    "get_system_info": "fmt_get_system_info",
    "run_command": "fmt_run_command",
    "read_file": "fmt_read_file",
    "list_directory": "fmt_list_directory",
    "search_files": "fmt_search_files",
    "list_processes": "fmt_list_processes",
    "grep_codebase": "fmt_grep_codebase",
    "list_recent_brain_changes": "fmt_list_recent_brain_changes",
    "get_chat_metrics": "fmt_get_chat_metrics",
    "semantic_memory_search": "fmt_semantic_memory_search",
    "get_technical_introspection": "fmt_get_technical_introspection",
}


def format_tool_result(
    tool: str,
    ok: bool,
    output: Any,
    error: Optional[str] = None,
) -> str:
    """Format a single tool result into a human-readable string.

    Pure function extracted from BrainSession._format_tool_result.
    Dispatches to the appropriate ``fmt_<name>`` function in this module via
    ``_TOOL_FORMATTER_FUNCS``.  Does NOT depend on ``BrainSession``.

    Parameters
    ----------
    tool : str
        Tool name (e.g. ``"check_port"``).
    ok : bool
        Whether the tool execution succeeded.
    output : Any
        Raw output from the tool (dict, list, str, etc.).
    error : Optional[str]
        Error message if the tool failed.
    """
    if not ok or output is None:
        return f"{tool}: error — {error or 'sin salida'}"
    if isinstance(output, (dict, list)):
        func_name = _TOOL_FORMATTER_FUNCS.get(tool)
        if func_name:
            try:
                formatter = globals().get(func_name)
                if formatter:
                    return formatter(output)
            except Exception as exc:
                logging.getLogger("session_fmt_helpers").warning(
                    "Formatter %s failed: %s", tool, exc, exc_info=True
                )
    if isinstance(output, dict):
        summary = output.get("summary") or output.get("message") or output.get("diagnosis")
        if isinstance(summary, str):
            return summary[:500]
        for code_field in ("content", "text", "source", "code", "body"):
            val = output.get(code_field)
            if isinstance(val, str) and len(val) > 240:
                nlines = val.count("\n") + 1
                head = val[:200].replace("\n", " \u23ce ")
                return (
                    f"{tool}: [{code_field} truncado: {len(val)} chars / "
                    f"{nlines} lineas] {head}..."
                )
        fields = []
        for key, value in output.items():
            if key in ("success", "raw"):
                continue
            if isinstance(value, (str, int, float, bool)):
                fields.append(f"{key}: {format_action_value(value)}")
            if len(fields) >= 6:
                break
        return ", ".join(fields) if fields else str(output)[:400]
    if isinstance(output, str):
        return output[:500]
    return str(output)[:400]
