"""
Brain Chat V9 — agent/tools.py
Herramientas estándar del agente: filesystem, código, sistema, web, HTTP.
Se registran en ToolExecutor para que AgentLoop las use.
"""
import ast
import asyncio
import json
import logging
import os
import re
import subprocess
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession, ClientTimeout

from brain_v9.agent.loop import ToolExecutor
from brain_v9.config import BASE_PATH
from brain_v9.brain.self_improvement import (
    create_staged_change as si_create_staged_change,
    get_self_improvement_ledger as si_get_self_improvement_ledger,
    promote_staged_change as si_promote_staged_change,
    rollback_change as si_rollback_change,
    validate_staged_change as si_validate_staged_change,
)

log = logging.getLogger("agent.tools")

_PERMISSIONS_PATH = BASE_PATH / "policy" / "permissions.json"
_FINANCIAL_CONTRACT_PATH = BASE_PATH / "workspace" / "brainlab" / "brainlab" / "contracts" / "financial_motor_contract_v1.json"


def _load_permissions_policy() -> Dict[str, Any]:
    try:
        if _PERMISSIONS_PATH.exists():
            return json.loads(_PERMISSIONS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("Failed to load permissions policy: %s", exc)
    return {}


def _load_financial_contract() -> Dict[str, Any]:
    try:
        if _FINANCIAL_CONTRACT_PATH.exists():
            return json.loads(_FINANCIAL_CONTRACT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("Failed to load financial contract: %s", exc)
    return {}


def _deny_roots() -> List[Path]:
    contract = _load_financial_contract()
    deny_roots = (
        contract.get("execution", {})
        .get("tooling", {})
        .get("deny_roots", [])
    )
    roots = []
    for item in deny_roots:
        try:
            roots.append(Path(str(item)).resolve())
        except Exception as exc:
            logging.getLogger("brain_v9.agent.tools").debug("Cannot resolve deny_root %r: %s", item, exc)
            continue
    return roots


def _requires_escalation(operation: str, motivo: str, scope: List[str] | None = None, level: str = "P3") -> Dict[str, Any]:
    return {
        "success": False,
        "status": "escalation_required",
        "permission_level": level,
        "operation": operation,
        "motivo": motivo,
        "scope": scope or [],
        "message": f"Escalamiento requerido ({level}) para: {operation}",
    }


def _path_under_any(path: Path, roots: List[Path]) -> bool:
    try:
        resolved = path.resolve()
    except Exception as exc:
        logging.getLogger("brain_v9.agent.tools").debug("Cannot resolve path %r: %s", path, exc)
        return False
    return any(str(resolved).startswith(str(root)) for root in roots)


# ─── Filesystem ───────────────────────────────────────────────────────────────
def _god_active() -> bool:
    """True si hay una sesion god mode activa (ContextVar del execution_gate)."""
    try:
        from brain_v9.governance.execution_gate import _active_god_session, get_gate
        sid = _active_god_session.get()
        if sid and get_gate().is_god_mode(sid):
            return True
    except Exception:
        pass
    return False


def _safe_path(path_str: str) -> Path:
    """Verifica que el path esté dentro de BASE_PATH. God mode bypassa."""
    p = Path(path_str)
    if not p.is_absolute():
        p = BASE_PATH / path_str   # resolve relative to BASE_PATH, not CWD
    p = p.resolve()
    if _god_active():
        # God mode: cualquier path absoluto resuelto es valido (audit lo registra aparte)
        try:
            log.warning("GOD_MODE bypass _safe_path: %s", p)
        except Exception:
            pass
        return p
    base = BASE_PATH.resolve()
    if not str(p).startswith(str(base)):
        raise PermissionError(f"Ruta fuera de BASE_PATH: {p}")
    return p


def _assert_write_allowed(path: Path) -> None:
    if _god_active():
        try:
            log.warning("GOD_MODE bypass _assert_write_allowed: %s", path)
        except Exception:
            pass
        return
    deny_roots = _deny_roots()
    if _path_under_any(path, deny_roots):
        raise PermissionError(f"Escritura denegada por contrato en ruta protegida: {path}")


async def read_file(path: str, encoding: str = "utf-8") -> str:
    """Lee un archivo de texto.

    R16: si la ruta es un DIRECTORIO, en vez de devolver PermissionError críptico
    (Windows) o IsADirectoryError, devuelve un listado del directorio en formato
    legible. Esto permite al agente recuperarse en un solo turno sin reintentar
    la misma ruta indefinidamente (bug observado 6+ veces con el mismo path).
    """
    p = _safe_path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe: {p}")
    if p.is_dir():
        # R16: auto-fallback a listing
        try:
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception as e:
            raise IsADirectoryError(
                f"'{p}' is a directory and listing failed: {e}. Use list_dir or search_files."
            )
        MAX_ENTRIES = 200
        truncated = len(entries) > MAX_ENTRIES
        sample = entries[:MAX_ENTRIES]
        lines = [f"[DIRECTORY LISTING] {p}",
                 f"[NOTE] read_file received a directory path; auto-listed contents.",
                 f"[HINT] To read a file inside, call read_file with the full file path.",
                 f"[COUNT] {len(entries)} entries{' (truncated to 200)' if truncated else ''}",
                 ""]
        for e in sample:
            try:
                if e.is_dir():
                    lines.append(f"  <DIR>  {e.name}/")
                else:
                    size = e.stat().st_size
                    lines.append(f"  <FILE> {e.name}  ({size} bytes)")
            except Exception:
                lines.append(f"  <?>    {e.name}")
        # R16: record the misuse so capability_governor / LLM can learn pattern
        try:
            import sys as _sys
            _sys.path.insert(0, "C:/AI_VAULT")
            from brain.capability_governor import get_capability_governor
            get_capability_governor().record_tool_failure(
                "read_file",
                reason="path_is_directory",
                available_tools=None,
            )
        except Exception:
            pass
        return "\n".join(lines)
    return p.read_text(encoding=encoding, errors="ignore")


async def edit_file(path: str, old_text: str, new_text: str) -> Dict:
    """Edicion quirurgica: reemplaza old_text por new_text en un archivo.

    Requisitos:
    - old_text debe existir EXACTAMENTE una vez en el archivo.
    - Si no se encuentra o aparece mas de una vez, falla sin modificar.
    - Crea backup automatico antes de modificar.
    """
    p = _safe_path(path)
    _assert_write_allowed(p)
    if not p.exists():
        raise FileNotFoundError(f"No existe: {p}")

    content = p.read_text(encoding="utf-8", errors="ignore")
    count = content.count(old_text)

    if count == 0:
        return {"success": False, "error": "old_text no encontrado en el archivo", "path": str(p)}
    if count > 1:
        return {"success": False, "error": f"old_text aparece {count} veces — debe ser unico", "path": str(p)}

    # Auto-backup
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = p.with_name(f"{p.name}.backup_{stamp}")
    backup.write_bytes(p.read_bytes())

    new_content = content.replace(old_text, new_text, 1)
    p.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "path": str(p),
        "backup": str(backup),
        "old_len": len(old_text),
        "new_len": len(new_text),
        "file_bytes": len(new_content.encode("utf-8")),
    }


async def grep_codebase(query: str, include: str = "*.py", max_results: int = 20) -> List[Dict]:
    """Busca un patron de texto en todos los archivos del codebase AI_VAULT/tmp_agent/brain_v9.

    Args:
        query: Texto a buscar (case-insensitive)
        include: Glob pattern de archivos a incluir (default *.py)
        max_results: Maximo de resultados
    Returns:
        Lista de {path, line, text, context_before, context_after}
    """
    root = BASE_PATH / "tmp_agent" / "brain_v9"
    if not root.is_dir():
        return [{"error": f"Directorio no existe: {root}"}]

    results = []
    query_lower = query.lower()

    for fpath in root.rglob(include):
        if not fpath.is_file() or "__pycache__" in str(fpath) or ".backup" in fpath.name:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lines = text.splitlines()
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                results.append({
                    "path": str(fpath),
                    "rel_path": str(fpath.relative_to(root)).replace("\\", "/"),
                    "line": i + 1,
                    "text": line.strip()[:200],
                    "context_before": lines[max(0, i-1)].strip()[:100] if i > 0 else "",
                    "context_after": lines[min(len(lines)-1, i+1)].strip()[:100] if i < len(lines)-1 else "",
                })
                if len(results) >= max_results:
                    return results
    return results


async def write_file(path: str, content: str, encoding: str = "utf-8") -> Dict:
    p = _safe_path(path)
    _assert_write_allowed(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return {"written": str(p), "bytes": len(content.encode(encoding))}


async def backup_file(path: str) -> Dict:
    p = _safe_path(path)
    _assert_write_allowed(p)
    if not p.exists():
        raise FileNotFoundError(f"No existe: {p}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = p.with_name(f"{p.name}.backup_{stamp}")
    backup.write_bytes(p.read_bytes())
    return {"success": True, "source": str(p), "backup": str(backup)}


# ─── Memoria semantica / metacognicion / introspeccion ───────────────────────
async def semantic_memory_status() -> Dict[str, Any]:
    from brain_v9.core.semantic_memory import get_semantic_memory
    return get_semantic_memory().status()


async def semantic_memory_search(query: str, top_k: int = 5) -> Dict[str, Any]:
    from brain_v9.core.semantic_memory import get_semantic_memory
    memory = get_semantic_memory()
    return {"ok": True, "query": query, "results": memory.search(query, top_k=top_k)}


async def semantic_memory_ingest(
    text: str,
    source: str = "manual",
    session_id: str = "default",
    kind: str = "note",
) -> Dict[str, Any]:
    from brain_v9.core.semantic_memory import get_semantic_memory
    return get_semantic_memory().ingest_text(text=text, source=source, session_id=session_id, kind=kind)


async def semantic_memory_ingest_session(session_id: str = "default", limit: int = 200) -> Dict[str, Any]:
    from brain_v9.core.semantic_memory import get_semantic_memory
    return get_semantic_memory().ingest_session_memory(session_id=session_id, limit=limit)


async def get_metacognition_status() -> Dict[str, Any]:
    from brain_v9.brain.metacognition import build_metacognition_status
    return build_metacognition_status()


async def audit_claims(text: str, evidence: str = "") -> Dict[str, Any]:
    from brain_v9.brain.metacognition import audit_response_claims
    return audit_response_claims(text, evidence=evidence)


async def get_gpu_status() -> Dict[str, Any]:
    from brain_v9.brain.technical_introspection import get_gpu_status as _get_gpu_status
    return _get_gpu_status()


async def get_technical_introspection() -> Dict[str, Any]:
    from brain_v9.brain.technical_introspection import build_introspection_status
    return build_introspection_status()


async def request_clarification(
    question: str = "Necesito que especifiques mejor el objetivo o el contexto operativo.",
    missing: str = "",
) -> Dict[str, Any]:
    """Devuelve una solicitud estructurada de aclaracion.

    Se usa como alias seguro cuando un planner antiguo pide una tool interactiva
    que ya no existe en el runtime actual.
    """
    return {
        "success": False,
        "needs_clarification": True,
        "question": question,
        "missing": missing or "objective_or_context",
    }


async def list_directory(path: str, pattern: str = "*") -> List[str]:
    p = _safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"No es un directorio: {p}")
    return sorted(str(f.relative_to(p)) for f in p.glob(pattern) if not f.name.startswith("."))


# R12.7: vendored / noise directories filtered by default to avoid drowning
# user-relevant code under thousands of dependency files.
_VENDORED_DIR_NAMES = frozenset({
    ".venv", "venv", "env", ".env",
    "node_modules", "__pycache__",
    ".git", ".svn", ".hg",
    "dist", "build", "site-packages",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".next", ".cache", ".idea", ".vscode",
    "bower_components", "vendor",
})


def _is_vendored_path(p: Path, base: Path) -> bool:
    try:
        rel_parts = p.relative_to(base).parts
    except ValueError:
        rel_parts = p.parts
    return any(part in _VENDORED_DIR_NAMES for part in rel_parts)


async def search_files(
    directory: str,
    pattern: str,
    content_search: Optional[str] = None,
    include_vendored: bool = False,
) -> Dict:
    """Busca archivos por nombre (glob) y opcionalmente por contenido.

    R12.2: Returns dict with explicit truncation metadata so the LLM knows
    when it has only seen a partial result set and can refine the query.
    R12.7: Skips vendored/noise dirs (.venv, node_modules, __pycache__, .git,
    site-packages, dist, build, ...) by default. Pass include_vendored=True
    to opt in.
    """
    base = _safe_path(directory)
    results: List[Dict[str, Any]] = []
    SOFT_CAP = 50
    HARD_SCAN_CAP = 5000  # walk-time safety to avoid huge filesystem scans
    scanned = 0
    truncated = False
    skipped_vendored = 0
    for f in base.rglob(pattern):
        scanned += 1
        if scanned > HARD_SCAN_CAP:
            truncated = True
            break
        if not include_vendored and _is_vendored_path(f, base):
            skipped_vendored += 1
            continue
        if f.is_file():
            entry: Dict[str, Any] = {"path": str(f), "size": f.stat().st_size}
            if content_search:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    lines = [
                        {"line": i + 1, "text": l.strip()}
                        for i, l in enumerate(text.splitlines())
                        if content_search.lower() in l.lower()
                    ]
                    if lines:
                        entry["matches"] = lines[:10]
                        results.append(entry)
                except Exception as exc:
                    log.debug("Content search failed for %s: %s", f, exc)
            else:
                results.append(entry)
            if len(results) >= SOFT_CAP:
                truncated = True
                break
    hint_parts: List[str] = []
    if truncated:
        hint_parts.append(
            f"Showing {len(results)} of possibly more matches. "
            "Refine 'pattern' or add 'content_search' to narrow results."
        )
    if skipped_vendored and not include_vendored:
        hint_parts.append(
            f"Skipped {skipped_vendored} files in vendored dirs "
            "(.venv, node_modules, __pycache__, site-packages, dist, build, .git, ...). "
            "Pass include_vendored=True to include them."
        )
    return {
        "success": True,
        "directory": str(base),
        "pattern": pattern,
        "content_search": content_search,
        "results": results,
        "returned": len(results),
        "truncated": truncated,
        "soft_cap": SOFT_CAP,
        "skipped_vendored": skipped_vendored,
        "include_vendored": include_vendored,
        "hint": " ".join(hint_parts) if hint_parts else None,
    }


# ─── Análisis de código Python ────────────────────────────────────────────────
async def analyze_python(path: str) -> Dict:
    """Analiza un archivo Python: clases, funciones, imports, complejidad básica."""
    source = await read_file(path)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"error": f"Syntax error: {e}", "path": path}

    classes   = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    imports_raw = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports_raw.extend(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            imports_raw.append(n.module or "")

    lines = source.splitlines()
    return {
        "path":            path,
        "lines":           len(lines),
        "classes":         classes,
        "functions":       functions,
        "imports":         list(set(imports_raw)),
        "complexity_hint": "high" if len(lines) > 500 else "medium" if len(lines) > 100 else "low",
    }


async def find_in_code(path: str, query: str, context_lines: int = 2) -> List[Dict]:
    """Grep semántico en un archivo fuente."""
    source = await read_file(path)
    lines  = source.splitlines()
    hits   = []
    for i, line in enumerate(lines):
        if query.lower() in line.lower():
            start = max(0, i - context_lines)
            end   = min(len(lines), i + context_lines + 1)
            hits.append({
                "line":    i + 1,
                "match":   line.strip(),
                "context": lines[start:end],
            })
    return hits[:30]


async def check_syntax(path: str) -> Dict:
    """Verifica sintaxis Python sin ejecutar."""
    source = await read_file(path)
    try:
        ast.parse(source)
        return {"valid": True, "path": path}
    except SyntaxError as e:
        return {"valid": False, "path": path, "error": str(e), "line": e.lineno}


async def validate_python_change(paths: List[str]) -> Dict:
    """
    Valida cambios Python con py_compile sobre uno o varios archivos.
    """
    resolved = [_safe_path(p) for p in paths]
    cmd = ["python", "-m", "py_compile", *[str(p) for p in resolved]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(BASE_PATH / "tmp_agent"))
        return {
            "success": result.returncode == 0,
            "validated_files": [str(p) for p in resolved],
            "returncode": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "validated_files": [str(p) for p in resolved], "error": "Timeout compilando cambios Python"}
    except Exception as e:
        return {"success": False, "validated_files": [str(p) for p in resolved], "error": str(e)}


async def create_staged_change(files: List[str], objective: str = "", change_type: str = "code_patch") -> Dict:
    try:
        return si_create_staged_change(files, objective, change_type)
    except Exception as e:
        return {"success": False, "error": str(e)}


async def validate_staged_change(change_id: str) -> Dict:
    try:
        result = si_validate_staged_change(change_id)
        result["success"] = result.get("passed", False)
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "change_id": change_id}


async def promote_staged_change(change_id: str) -> Dict:
    try:
        return si_promote_staged_change(change_id)
    except Exception as e:
        return {"success": False, "error": str(e), "change_id": change_id}


async def rollback_staged_change(change_id: str) -> Dict:
    try:
        return si_rollback_change(change_id)
    except Exception as e:
        return {"success": False, "error": str(e), "change_id": change_id}


async def get_self_improvement_ledger() -> Dict:
    try:
        return si_get_self_improvement_ledger()
    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_recent_brain_changes(days: int = 7, max_files: int = 100) -> Dict:
    """List ALL recent changes to the Brain — both formal ledger entries AND
    raw file modifications on disk. This is the canonical answer to "have you
    had recent improvements?" because it captures changes made outside the
    self_improve_cycle path (manual edits, hardenings, hotfixes).

    Returns:
      {
        success: True,
        days_window: int,
        ledger_recent: [...],     # entries from self-improvement ledger within window
        ledger_total: int,
        file_changes: [           # files modified within window, sorted newest-first
          {path, mtime_iso, size_bytes, age_hours, area},
          ...
        ],
        summary: str,             # human-readable one-line summary
      }
    """
    import os
    from datetime import datetime, timedelta

    try:
        days = max(1, min(int(days), 90))
    except Exception:
        days = 7
    try:
        max_files = max(1, min(int(max_files), 100))
    except Exception:
        max_files = 25

    cutoff = datetime.now() - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    # Critical brain code areas to scan
    scan_roots = [
        (r"C:\AI_VAULT\brain", "brain_core"),
        (r"C:\AI_VAULT\tmp_agent\brain_v9\agent", "brain_v9_agent"),
        (r"C:\AI_VAULT\tmp_agent\brain_v9\brain", "brain_v9_brain"),
        (r"C:\AI_VAULT\tmp_agent\brain_v9\governance", "brain_v9_governance"),
        (r"C:\AI_VAULT\tmp_agent\brain_v9\core", "brain_v9_core"),
        (r"C:\AI_VAULT\scripts", "scripts"),
    ]

    file_changes = []
    skip_dirs = {"__pycache__", ".git", "node_modules", "_archived_orphans"}
    valid_exts = {".py", ".ps1", ".json", ".md", ".yaml", ".yml"}

    for root, area in scan_roots:
        if not os.path.isdir(root):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in valid_exts:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    try:
                        st = os.stat(fpath)
                    except OSError:
                        continue
                    if st.st_mtime < cutoff_ts:
                        continue
                    age_hours = (datetime.now().timestamp() - st.st_mtime) / 3600.0
                    file_changes.append({
                        "path": fpath,
                        "mtime_iso": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                        "size_bytes": st.st_size,
                        "age_hours": round(age_hours, 2),
                        "area": area,
                    })
        except Exception:
            continue

    file_changes.sort(key=lambda x: x["mtime_iso"], reverse=True)
    file_changes_capped = file_changes[:max_files]

    # Pull formal ledger entries
    ledger_recent = []
    ledger_total = 0
    try:
        ledger = si_get_self_improvement_ledger()
        entries = ledger.get("entries", []) if isinstance(ledger, dict) else []
        ledger_total = len(entries)
        for e in entries:
            ts = e.get("timestamp") or e.get("ts") or ""
            try:
                t = datetime.fromisoformat(ts.replace("Z", ""))
                if t >= cutoff:
                    ledger_recent.append(e)
            except Exception:
                continue
    except Exception:
        pass

    summary = (
        f"En los ultimos {days} dias: {len(file_changes)} archivos modificados "
        f"({len(ledger_recent)} via ledger formal, {len(file_changes) - len(ledger_recent)} edits directos). "
        f"Mas reciente: {file_changes[0]['path']} @ {file_changes[0]['mtime_iso']}"
        if file_changes else
        f"Sin cambios en los ultimos {days} dias."
    )

    return {
        "success": True,
        "days_window": days,
        "ledger_recent": ledger_recent,
        "ledger_total": ledger_total,
        "file_changes": file_changes_capped,
        "file_changes_total": len(file_changes),
        "summary": summary,
    }


# ─── Sistema ──────────────────────────────────────────────────────────────────
async def get_system_info() -> Dict:
    try:
        import psutil
        return {
            "cpu_percent":    psutil.cpu_percent(interval=0.5),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent":   psutil.disk_usage("/").percent,
        }
    except ImportError:
        return {"note": "psutil no disponible"}


async def _run_internal_command(cmd: str, cwd: Optional[str] = None, timeout: int = 30) -> Dict:
    """Internal subprocess helper for vetted runtime operations.

    R12.2/R12.5: Surfaces output truncation flags and the exception type / tail
    traceback so the agent's failure_feedback layer can produce actionable hints
    instead of a bare 'Error desconocido'.

    R17: detect dangerous PowerShell-via-cmd patterns and provide actionable
    hint instead of letting Windows mangle '$' / '$_' / '$env:' variables.
    """
    STDOUT_CAP = 8000
    STDERR_CAP = 2000
    # R17: hint when invoking PowerShell with -Command and dollar-vars
    cmd_lower = cmd.lower()
    if (("powershell" in cmd_lower or "pwsh" in cmd_lower)
            and "-command" in cmd_lower
            and "$" in cmd):
        return {
            "success": False,
            "error": ("R17: PowerShell -Command con '$' detectado. cmd.exe + PowerShell "
                      "-Command suele mangle variables ($_, $env:, $LASTEXITCODE). "
                      "Escribe el script a un .ps1 y usa 'run_powershell' (file=...) "
                      "o invoca con -File en vez de -Command."),
            "error_type": "PowerShellCommandWithDollar",
            "hint": "use run_powershell(file_path=...) o powershell -ExecutionPolicy Bypass -File <path>.ps1",
            "cmd_preview": cmd[:200],
        }
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        out = result.stdout or ""
        err = result.stderr or ""
        return {
            "success": result.returncode == 0,
            "stdout": out[:STDOUT_CAP],
            "stderr": err[:STDERR_CAP],
            "returncode": result.returncode,
            "stdout_truncated": len(out) > STDOUT_CAP,
            "stderr_truncated": len(err) > STDERR_CAP,
            "stdout_full_len": len(out),
            "stderr_full_len": len(err),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "success": False,
            "error": f"Timeout ({timeout}s) ejecutando: {cmd[:100]}",
            "error_type": "TimeoutExpired",
            "timeout_s": timeout,
        }
    except Exception as e:
        import traceback as _tb
        return {
            "success": False,
            "error": (str(e) or repr(e))[:500],
            "error_type": type(e).__name__,
            "traceback_tail": _tb.format_exc()[-400:],
        }


async def run_powershell(file_path: Optional[str] = None,
                         script: Optional[str] = None,
                         args: Optional[List[str]] = None,
                         cwd: Optional[str] = None,
                         timeout: int = 60) -> Dict:
    """R17: ejecuta PowerShell de forma robusta evitando el doble parsing
    cmd.exe + PowerShell que destruye variables '$'.

    Modos:
      - file_path='C:/path/script.ps1' : ejecuta el .ps1 directamente.
      - script='Get-Process; ...'      : escribe a temp .ps1 y ejecuta.

    Usa subprocess con argv list (shell=False) y -ExecutionPolicy Bypass -File.
    """
    import tempfile as _tmp
    STDOUT_CAP = 8000
    STDERR_CAP = 2000
    if not file_path and not script:
        return {"success": False, "error": "must provide file_path or script",
                "error_type": "ValueError"}
    cleanup_path: Optional[str] = None
    try:
        if not file_path and script:
            # Write to temp .ps1 (ASCII-safe; document this)
            try:
                script.encode("ascii")
            except UnicodeEncodeError:
                return {"success": False,
                        "error": "R17: script contiene caracteres no-ASCII; "
                                 "PowerShell parser falla. Usa file_path=... con encoding controlado.",
                        "error_type": "NonAsciiScript"}
            fh = _tmp.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="ascii")
            fh.write(script)
            fh.close()
            file_path = fh.name
            cleanup_path = file_path
        else:
            # Validate path
            p = _safe_path(file_path)  # type: ignore[arg-type]
            if not p.exists() or not p.is_file():
                return {"success": False,
                        "error": f"file_path no existe o no es archivo: {p}",
                        "error_type": "FileNotFoundError"}
            file_path = str(p)
        argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", file_path]
        if args:
            argv.extend([str(a) for a in args])
        result = subprocess.run(
            argv, shell=False, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        out = result.stdout or ""
        err = result.stderr or ""
        return {
            "success": result.returncode == 0,
            "stdout": out[:STDOUT_CAP],
            "stderr": err[:STDERR_CAP],
            "returncode": result.returncode,
            "stdout_truncated": len(out) > STDOUT_CAP,
            "stderr_truncated": len(err) > STDERR_CAP,
            "argv": argv,
            "method": "powershell -File (no shell, no double-parse)",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s) en run_powershell",
                "error_type": "TimeoutExpired", "timeout_s": timeout}
    except Exception as e:
        import traceback as _tb
        return {"success": False, "error": (str(e) or repr(e))[:500],
                "error_type": type(e).__name__,
                "traceback_tail": _tb.format_exc()[-400:]}
    finally:
        if cleanup_path:
            try:
                import os as _os
                _os.unlink(cleanup_path)
            except Exception:
                pass


async def run_command(cmd: str, cwd: Optional[str] = None, timeout: int = 30) -> Dict:
    """
    Ejecuta un comando de shell.
    Seguridad via ExecutionGate: clasifica riesgo P0-P3 y aplica gate segun modo.

    R26: si el comando falla por binario faltante (e.g. nmap), inyecta
    `native_alternative` con la herramienta nativa equivalente; para nmap
    ejecuta auto-fallback a scan_local_network y devuelve resultado fusionado.
    """
    from brain_v9.governance.execution_gate import get_gate

    gate = get_gate()
    decision = gate.check("run_command", {"cmd": cmd, "cwd": cwd})

    if not decision["allowed"]:
        return {
            "success": False,
            "error": decision["reason"],
            "risk": decision["risk"],
            "action": decision["action"],
            "pending_id": decision.get("pending_id"),
        }

    result = await _run_internal_command(cmd, cwd=cwd, timeout=timeout)

    # R26: post-procesado de fallback nativo
    if not result.get("success"):
        try:
            result = await _maybe_native_fallback(cmd, result)
        except Exception as _e:
            result.setdefault("native_fallback_error", str(_e)[:200])
    return result


# R26: mapping binario faltante -> herramienta nativa equivalente
_NATIVE_FALLBACKS: Dict[str, Dict[str, str]] = {
    "nmap":       {"tool": "scan_local_network", "hint": "scan_local_network(cidr='X.X.X.X/Y') hace TCP sweep sin nmap"},
    "ping":       {"tool": "scan_local_network", "hint": "scan_local_network(cidr=...) detecta hosts vivos via TCP"},
    "tracert":    {"tool": "detect_local_network", "hint": "detect_local_network() devuelve interfaces y gateway"},
    "traceroute": {"tool": "detect_local_network", "hint": "detect_local_network() devuelve interfaces y gateway"},
    "ipconfig":   {"tool": "detect_local_network", "hint": "detect_local_network() lista IPs/CIDR/gateway"},
    "ifconfig":   {"tool": "detect_local_network", "hint": "detect_local_network() lista IPs/CIDR/gateway"},
    "curl":       {"tool": "check_http_service",  "hint": "check_http_service(url='https://...') hace GET HTTP"},
    "wget":       {"tool": "check_http_service",  "hint": "check_http_service(url='https://...') hace GET HTTP"},
    "netstat":    {"tool": "check_port",          "hint": "check_port(port=N) inspecciona puerto en Windows"},
}


def _detect_missing_binary(cmd: str, stderr: str) -> Optional[str]:
    """Devuelve el nombre del binario faltante si stderr indica 'not recognized'/'not found'."""
    if not stderr:
        return None
    import re as _re
    patterns = [
        r"'([^']+)' is not recognized",
        r'"([^"]+)" is not recognized',
        r"^([\w\.\-]+):\s*command not found",
        r"command not found:\s*([\w\.\-]+)",
        r'exec:\s*"?([\w\.\-]+)"?:\s*executable file not found',
        r"No such file or directory:\s*'?([\w\.\-]+)'?",
    ]
    for p in patterns:
        m = _re.search(p, stderr, _re.IGNORECASE | _re.MULTILINE)
        if m:
            name = m.group(1).strip().lower()
            if name.endswith(".exe"):
                name = name[:-4]
            # strip path
            if "/" in name:
                name = name.rsplit("/", 1)[-1]
            if "\\" in name:
                name = name.rsplit("\\", 1)[-1]
            return name
    # fallback: first token of cmd if stderr mentions "not recognized" sin parsear nombre
    if "not recognized" in stderr.lower() or "command not found" in stderr.lower():
        first = cmd.strip().split()[0].lower() if cmd.strip() else ""
        if first.endswith(".exe"):
            first = first[:-4]
        return first or None
    return None


def _extract_cidr_from_cmd(cmd: str) -> Optional[str]:
    import re as _re
    m = _re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\b", cmd)
    if m:
        return m.group(1)
    # IP sola → /32
    m = _re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", cmd)
    if m:
        return m.group(1) + "/32"
    return None


async def _maybe_native_fallback(cmd: str, result: Dict) -> Dict:
    """R26: si result indica binario faltante y existe equivalente nativo,
    sugierelo (siempre) y auto-ejecutalo cuando el mapping es 1:1 obvio (nmap)."""
    stderr = result.get("stderr") or result.get("error") or ""
    binary = _detect_missing_binary(cmd, stderr)
    if not binary:
        return result
    fb = _NATIVE_FALLBACKS.get(binary)
    if not fb:
        return result
    result["missing_binary"] = binary
    result["native_alternative"] = fb["tool"]
    result["native_alternative_hint"] = fb["hint"]
    # Auto-ejecucion solo para nmap (mapping 1:1 con scan_local_network)
    if binary == "nmap":
        cidr = _extract_cidr_from_cmd(cmd)
        try:
            sub = await scan_local_network(cidr=cidr) if cidr else await scan_local_network()
            result["auto_fallback_used"] = "scan_local_network"
            result["auto_fallback_result"] = sub
            # Si el fallback fue OK, marcamos success=True para que el agente NO trate esto como fallo
            if sub.get("success"):
                result["success"] = True
                live = sub.get("live_hosts") or sub.get("live") or sub.get("hosts") or []
                summary = (
                    f"nmap no disponible; scan_local_network nativo escaneo {sub.get('cidr')} "
                    f"y detecto {len(live)} hosts vivos."
                )
                result["fallback_summary"] = summary
                # R26: poner el resumen + datos en stdout para que el LLM los vea
                # como output normal al construir la respuesta final.
                hosts_brief = ""
                if live:
                    sample = live[:20]
                    hosts_brief = "\nHosts detectados: " + ", ".join(
                        h.get("ip", "?") for h in sample if isinstance(h, dict)
                    )
                    if len(live) > 20:
                        hosts_brief += f" ... (+{len(live)-20} mas)"
                result["stdout"] = summary + hosts_brief
                result["returncode"] = 0
                result["error"] = None
        except Exception as e:
            result["auto_fallback_error"] = str(e)[:300]
    return result


# ─── HTTP / Network ───────────────────────────────────────────────────────────
async def check_http_service(url: str, timeout: int = 5) -> Dict:
    """
    Verifica si un servicio HTTP está respondiendo.
    Útil para diagnosticar dashboards, APIs, bridges, etc.
    """
    try:
        t0 = time.time()
        async with ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                elapsed_ms = (time.time() - t0) * 1000
                return {
                    "success": True,
                    "url": url,
                    "status_code": response.status,
                    "is_healthy": response.status < 400,
                    "response_time_ms": round(elapsed_ms, 2),
                    "error": None
                }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "status_code": None,
            "is_healthy": False,
            "response_time_ms": None,
            "error": str(e),
            "error_type": type(e).__name__
        }


async def call_brain_api(path: str, method: str = "GET", payload: Optional[Dict] = None, timeout: int = 15) -> Dict:
    """Calls the live Brain V9 runtime on :8090 and returns parsed JSON."""
    clean_path = path if path.startswith("/") else f"/{path}"
    url = f"http://127.0.0.1:8090{clean_path}"
    try:
        async with ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            if method.upper() == "POST":
                async with session.post(url, json=payload) as response:
                    data = await response.json(content_type=None)
                    return {
                        "success": response.status < 400,
                        "url": url,
                        "status_code": response.status,
                        "data": data,
                    }
            async with session.get(url) as response:
                data = await response.json(content_type=None)
                return {
                    "success": response.status < 400,
                    "url": url,
                    "status_code": response.status,
                    "data": data,
                }
    except Exception as e:
        return {"success": False, "url": url, "status_code": None, "error": str(e)}


async def check_port_status(host: str, port: int) -> Dict:
    """
    Verifica si un puerto está abierto y escuchando conexiones.
    """
    try:
        t0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        elapsed_ms = (time.time() - t0) * 1000
        
        if result == 0:
            return {
                "success": True,
                "host": host,
                "port": port,
                "is_open": True,
                "response_time_ms": round(elapsed_ms, 2),
                "diagnosis": f"Puerto {port} está abierto en {host}",
                "error": None
            }
        else:
            return {
                "success": True,
                "host": host,
                "port": port,
                "is_open": False,
                "diagnosis": f"Puerto {port} está cerrado en {host}. El servicio no está corriendo.",
                "error": f"Socket error code: {result}"
            }
    except Exception as e:
        return {
            "success": False,
            "host": host,
            "port": port,
            "is_open": False,
            "diagnosis": f"Error al verificar puerto {port}: {str(e)}",
            "error": str(e)
        }


async def diagnose_dashboard() -> Dict:
    """
    Diagnóstico del dashboard — ahora integrado en Brain V9 en :8090/ui.
    Port 8070 is retired. dashboard_professional/ was removed in P5-11.
    """
    results = {
        "service": "Dashboard (integrado en Brain V9 :8090/ui)",
        "checks": []
    }

    # Check Brain V9 on port 8090
    port_check = await check_port_status("127.0.0.1", 8090)
    results["checks"].append({
        "name": "Verificar puerto 8090 (Brain V9)",
        "result": port_check
    })

    if port_check["is_open"]:
        http_check = await check_http_service("http://127.0.0.1:8090/health")
        results["checks"].append({
            "name": "Verificar HTTP /health",
            "result": http_check
        })
        results["summary"] = "Dashboard integrado en Brain V9 :8090/ui"
        results["recommendation"] = "Acceder a http://localhost:8090/ui"
    else:
        results["summary"] = "Brain V9 no esta corriendo en puerto 8090"
        results["recommendation"] = "Ejecutar emergency_start.ps1 para iniciar Brain V9"

    return results


# ─── Windows / Servicios Específicos ─────────────────────────────────────────
async def check_port(port: int) -> Dict:
    """Verifica qué proceso usa un puerto específico en Windows."""
    result = await _run_internal_command(f"netstat -ano | findstr :{port}")
    if not result.get("stdout", "").strip():
        return {"success": True, "port": port, "status": "libre", "processes": []}

    lines = result["stdout"].strip().splitlines()
    processes = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 5:
            processes.append({
                "proto":   parts[0],
                "local":   parts[1],
                "foreign": parts[2],
                "state":   parts[3] if len(parts) > 4 else "",
                "pid":     parts[-1],
            })

    # Intentar resolver nombres de proceso
    pids = list({p["pid"] for p in processes if p["pid"].isdigit()})
    for pid in pids[:5]:
        name_result = await _run_internal_command(f'tasklist /FI "PID eq {pid}" /FO CSV /NH')
        if name_result.get("success") and name_result.get("stdout"):
            for proc in processes:
                if proc["pid"] == pid:
                    proc["name"] = name_result["stdout"].split(",")[0].strip('"')

    return {
        "success":   True,
        "port":      port,
        "status":    "en_uso",
        "processes": processes,
        "raw":       result["stdout"],
    }


async def list_processes(filter_name: str = "") -> Dict:
    """Lista procesos corriendo en Windows, opcionalmente filtrados por nombre.

    R12.4: usa csv.reader para parsear correctamente líneas con quotes/comas
    embebidos (servicios con descripciones, etc) que el split crudo descartaba.
    R12.2: emite metadata de truncado.
    """
    cmd = "tasklist /FO CSV /NH"
    if filter_name:
        cmd = f'tasklist /FI "IMAGENAME eq {filter_name}" /FO CSV /NH'
    result = await _run_internal_command(cmd)
    if not result.get("success"):
        return result

    import csv as _csv
    import io as _io
    SOFT_CAP = 30
    processes: List[Dict[str, Any]] = []
    raw = result.get("stdout", "") or ""
    try:
        reader = _csv.reader(_io.StringIO(raw))
        for row in reader:
            if len(row) >= 2:
                processes.append({
                    "name": row[0],
                    "pid": row[1],
                    "session": row[2] if len(row) > 2 else None,
                    "mem": row[4] if len(row) > 4 else None,
                })
    except Exception as exc:
        return {
            "success": False,
            "error": f"CSV parse error: {exc}",
            "error_type": type(exc).__name__,
            "raw_sample": raw[:300],
        }

    total = len(processes)
    truncated = total > SOFT_CAP
    return {
        "success": True,
        "count": total,
        "returned": min(total, SOFT_CAP),
        "truncated": truncated,
        "processes": processes[:SOFT_CAP],
        "filter_name": filter_name or None,
        "hint": (
            f"Showing top {SOFT_CAP} of {total} procesos. "
            "Pasa filter_name='<exe.name>' para acotar."
        ) if truncated else None,
    }


async def check_url(url: str, timeout: int = 5) -> Dict:
    """Verifica si una URL responde (útil para verificar servicios web)."""
    result = await _run_internal_command(
        f'curl -s -o NUL -w "%%{{http_code}}" --max-time {timeout} {url}',
        timeout=timeout + 2
    )
    code = result.get("stdout", "").strip()
    return {
        "success":     result.get("success", False),
        "url":         url,
        "http_code":   code,
        "reachable":   code.startswith("2") or code.startswith("3"),
        "status":      "online" if (code.startswith("2") or code.startswith("3")) else "offline",
    }


async def find_dashboard_files(base_path: str = "C:\\AI_VAULT") -> Dict:
    """Busca todos los archivos de dashboard en el ecosistema Brain."""
    result = await _run_internal_command(
        f'dir /s /b "{base_path}\\*dashboard*" 2>nul',
    )
    files = [f.strip() for f in result.get("stdout", "").splitlines() if f.strip()]
    py_files  = [f for f in files if f.endswith(".py")]
    html_files = [f for f in files if f.endswith(".html")]

    return {
        "success":    True,
        "total":      len(files),
        "python":     py_files,
        "html":       html_files,
        "all_files":  files[:20],
    }


# ─── Iniciar servicios ───────────────────────────────────────────────────────
async def start_dashboard() -> Dict:
    """Dashboard is now integrated into Brain V9 at :8090/ui.
    Port 8070 and dashboard_professional/ were retired in P5-11."""
    check = await check_port(8090)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Dashboard integrado en Brain V9 — http://localhost:8090/ui",
            "status": "already_running",
            "url": "http://localhost:8090/ui",
        }
    return {
        "success": False,
        "message": "Brain V9 no esta corriendo. Ejecutar emergency_start.ps1",
        "status": "brain_v9_not_running",
        "url": "http://localhost:8090/ui",
    }


async def start_brain_server() -> Dict:
    """Inicia el servidor Brain Chat V9."""
    import os
    brain_dir = r"C:\AI_VAULT\tmp_agent"
    
    # Verificar si ya está corriendo
    check = await check_port(8090)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Brain Chat V9 ya está corriendo en el puerto 8090",
            "status": "already_running"
        }
    
    # Iniciar el servidor
    result = await _run_internal_command(
        'start /B python -m brain_v9.main > brain_server.log 2>&1',
        cwd=brain_dir
    )
    
    if result.get("success"):
        import asyncio
        await asyncio.sleep(3)
        verify = await check_port(8090)
        
        if verify.get("status") == "en_uso":
            return {
                "success": True,
                "message": "Brain Chat V9 iniciado correctamente en http://localhost:8090",
                "status": "started",
                "url": "http://localhost:8090"
            }
        else:
            return {
                "success": False,
                "error": "El comando se ejecutó pero el puerto 8090 sigue libre",
                "status": "failed_to_start"
            }
    else:
        return {
            "success": False,
            "error": f"Error al iniciar: {result.get('stderr', 'Error desconocido')}",
            "status": "error"
        }


async def restart_brain_v9_safe(wait_seconds: int = 25) -> Dict:
    """
    Reinicia Brain V9 usando un helper externo para no matar la request actual.
    El helper espera unos segundos, detiene 8090, levanta V9 y verifica /health.
    """
    ops_dir = BASE_PATH / "tmp_agent" / "brain_v9" / "ops"
    ops_dir.mkdir(parents=True, exist_ok=True)
    helper = ops_dir / "restart_brain_v9_safe.ps1"
    artifact = ops_dir / f"restart_brain_v9_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    script = f"""$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 3
$artifact = '{artifact}'
$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {{
  try {{ Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }} catch {{}}
}}
Start-Sleep -Seconds 2
$env:PYTHONUNBUFFERED = '1'
$p = Start-Process -FilePath python -ArgumentList '-u','-m','brain_v9.main' -WorkingDirectory 'C:\\AI_VAULT\\tmp_agent' -WindowStyle Hidden -PassThru
$ok = $false
$status = $null
for ($i = 0; $i -lt {wait_seconds}; $i++) {{
  Start-Sleep -Seconds 1
  try {{
    $resp = Invoke-RestMethod 'http://127.0.0.1:8090/health' -TimeoutSec 3
    $status = $resp.status
    if ($resp.status -eq 'healthy') {{ $ok = $true; break }}
  }} catch {{}}
}}
@{{
  ok = $ok
  pid = $p.Id
  health_status = $status
  artifact_generated_at = (Get-Date).ToString('s')
}} | ConvertTo-Json -Depth 4 | Set-Content $artifact -Encoding UTF8
"""
    helper.write_text(script, encoding="utf-8")
    try:
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "success": True,
            "status": "restart_scheduled",
            "helper": str(helper),
            "artifact": str(artifact),
            "note": "El helper externo reiniciará V9 y escribirá el resultado en el artifact.",
        }
    except Exception as e:
        return {"success": False, "status": "restart_schedule_failed", "error": str(e), "helper": str(helper)}


async def get_dashboard_data(endpoint: str = "status") -> Dict:
    """
    Obtiene datos del dashboard de autonomia integrado en Brain V9 (:8090).

    R14.1: Endpoints viven en la raiz (sin prefijo /api/). Acepta endpoint con
    o sin / inicial. Ej: 'status', 'brain/strategy-engine/ranking',
    'brain/validators'.

    Args:
        endpoint: API endpoint a consultar (sin /api/ prefix).

    Returns:
        Dict con los datos del dashboard o error estructurado.
    """
    import aiohttp
    ep = endpoint.lstrip("/")
    # R14.1: backward compat - if caller still passes 'api/...' strip it
    if ep.startswith("api/"):
        ep = ep[4:]
    url = f"http://localhost:8090/{ep}"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "endpoint": ep,
                        "url": url,
                        "data": data,
                        "status_code": response.status
                    }
                else:
                    body_preview = (await response.text())[:200]
                    return {
                        "success": False,
                        "endpoint": ep,
                        "url": url,
                        "error_type": "http_error",
                        "error": f"HTTP {response.status}",
                        "body_preview": body_preview,
                        "status_code": response.status,
                        "hint": (
                            f"Endpoint '{ep}' returned {response.status}. "
                            "Verify the path exists (no /api/ prefix). "
                            "Common: 'status', 'brain/strategy-engine/ranking', "
                            "'brain/validators', 'tools/coverage'."
                        ),
                    }
    except Exception as e:
        return {
            "success": False,
            "endpoint": endpoint,
            "error": str(e),
            "status_code": None
        }


async def get_live_autonomy_status() -> Dict:
    """Reads the current autonomy/runtime state from the live Brain V9 API."""
    health = await call_brain_api("/health")
    strategy = await call_brain_api("/brain/strategy-engine/summary")
    utility = await call_brain_api("/brain/utility/v2/refresh", method="POST", payload={})
    meta_governance = await call_brain_api("/brain/meta-governance/status?refresh=true")
    next_actions_path = BASE_PATH / "tmp_agent" / "state" / "autonomy_next_actions.json"
    try:
        next_actions = json.loads(next_actions_path.read_text(encoding="utf-8")) if next_actions_path.exists() else {}
    except Exception as exc:
        log.debug("Failed reading autonomy_next_actions.json: %s", exc)
        next_actions = {}
    return {
        "success": bool(health.get("success")),
        "brain_health": health.get("data"),
        "strategy_summary": strategy.get("data"),
        "utility": utility.get("data"),
        "meta_governance": meta_governance.get("data"),
        "next_actions": next_actions,
    }


async def execute_top_action_live(force: bool = False) -> Dict:
    """Executes the current top autonomy action against the live Brain runtime."""
    suffix = "true" if force else "false"
    return await call_brain_api(f"/brain/autonomy/execute-top-action?force={suffix}", method="POST", payload={})


async def get_strategy_engine_live() -> Dict:
    """Returns the current strategy-engine summary from the live Brain runtime."""
    return await call_brain_api("/brain/strategy-engine/summary")


async def get_edge_validation_live() -> Dict:
    """Returns the current canonical edge-validation snapshot from the live Brain runtime."""
    return await call_brain_api("/brain/strategy-engine/edge-validation")


async def get_strategy_ranking_v2_live() -> Dict:
    """Returns the current canonical ranking-v2 snapshot from the live Brain runtime."""
    return await call_brain_api("/brain/strategy-engine/ranking-v2")


async def get_pipeline_integrity_live() -> Dict:
    """Returns the current canonical trading pipeline integrity snapshot from the live Brain runtime."""
    return await call_brain_api("/brain/strategy-engine/pipeline-integrity")


async def get_risk_status_live(refresh: bool = True) -> Dict:
    """Returns the current canonical financial risk-contract status from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/risk/status?refresh={suffix}")


async def get_governance_health_live(refresh: bool = True) -> Dict:
    """Returns the current canonical governance-health snapshot from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/governance/health?refresh={suffix}")


async def get_post_trade_hypotheses_live(include_llm: bool = True) -> Dict:
    """Returns the current canonical post-trade hypothesis synthesis from the live Brain runtime."""
    suffix = "true" if include_llm else "false"
    return await call_brain_api(f"/brain/strategy-engine/post-trade-hypotheses?include_llm={suffix}")


async def get_security_posture_live(refresh: bool = True) -> Dict:
    """Returns the current canonical security posture from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/security/posture?refresh={suffix}")


async def get_change_control_live(refresh: bool = True) -> Dict:
    """Returns the current canonical change-control scorecard from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/change-control/scorecard?refresh={suffix}")


async def get_control_layer_live(refresh: bool = True) -> Dict:
    """Returns the current canonical control-layer / kill-switch status from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/control-layer/status?refresh={suffix}")


async def get_meta_governance_live(refresh: bool = True) -> Dict:
    """Returns the current canonical meta-governance / priority state from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/meta-governance/status?refresh={suffix}")


async def get_session_memory_live(session_id: str = "default", refresh: bool = True) -> Dict:
    """Returns the current canonical session-memory snapshot from the live Brain runtime."""
    suffix = "true" if refresh else "false"
    return await call_brain_api(f"/brain/session-memory?session_id={session_id}&refresh={suffix}")


async def refresh_strategy_engine_live() -> Dict:
    """Refreshes strategy-engine snapshots and returns the new state."""
    return await call_brain_api("/brain/strategy-engine/refresh", method="POST", payload={})


async def execute_strategy_candidate_live(strategy_id: str) -> Dict:
    """Executes a concrete strategy candidate in the live Brain runtime."""
    return await call_brain_api(f"/brain/strategy-engine/execute-candidate/{strategy_id}", method="POST", payload={})


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1: SERVICIOS DEL ECOSISTEMA AI_VAULT (8 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def start_brain_v7() -> Dict:
    """Inicia Brain Chat V7/V8 (legacy) en puerto alternativo 8095."""
    return _requires_escalation(
        operation="start_brain_v7",
        motivo="Servicio legacy fuera del runtime canónico y alojado en raíz protegida.",
        scope=[r"C:\AI_VAULT\00_identity\chat_brain_v7"],
        level="P3",
    )


async def start_dashboard_autonomy() -> Dict:
    """Dashboard de Autonomia is now integrated into Brain V9 at :8090/ui.
    Port 8070 was retired in P5-11."""
    check = await check_port(8090)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Dashboard de Autonomia integrado en Brain V9 — http://localhost:8090/ui",
            "status": "already_running",
            "url": "http://localhost:8090/ui",
        }
    return {
        "success": False,
        "message": "Brain V9 no esta corriendo. Ejecutar emergency_start.ps1",
        "status": "brain_v9_not_running",
        "url": "http://localhost:8090/ui",
    }


async def start_brain_server_legacy() -> Dict:
    """Inicia Brain Server legacy en puerto 8000."""
    return _requires_escalation(
        operation="start_brain_server_legacy",
        motivo="Servicio legacy en puerto 8000, fuera del runtime canónico y alojado en 00_identity.",
        scope=[r"C:\AI_VAULT\00_identity\brain_server.py"],
        level="P3",
    )


async def start_advisor_server() -> Dict:
    """Inicia Advisor Server en puerto 8010."""
    return _requires_escalation(
        operation="start_advisor_server",
        motivo="Servicio alojado en 00_identity, fuera del scope canónico de operación del agente.",
        scope=[r"C:\AI_VAULT\00_identity\advisor_server.py"],
        level="P3",
    )


async def check_service_status(service_name: str = "all") -> Dict:
    """Verifica el estado de los servicios del ecosistema AI_VAULT."""
    services = {
        "brain_v9": {"port": 8090, "name": "Brain Chat V9"},
        "brain_v7": {"port": 8095, "name": "Brain V7/V8"},
        "brain_server": {"port": 8000, "name": "Brain Server Legacy"},
        "advisor_server": {"port": 8010, "name": "Advisor Server"},
    }
    
    results = {}
    for svc_id, svc_info in services.items():
        if service_name != "all" and svc_id != service_name:
            continue
        check = await check_port(svc_info["port"])
        results[svc_id] = {"name": svc_info["name"], "port": svc_info["port"], "status": "running" if check.get("status") == "en_uso" else "stopped"}
    
    return {"success": True, "services_checked": len(results), "services": results}


async def stop_service(service_name: str) -> Dict:
    """Detiene un servicio del ecosistema por nombre."""
    return _requires_escalation(
        operation=f"stop_service:{service_name}",
        motivo="Detener procesos/servicios del ecosistema es una operación P3 de alto impacto.",
        scope=[service_name],
        level="P3",
    )


async def restart_service(service_name: str) -> Dict:
    """Reinicia un servicio del ecosistema."""
    return _requires_escalation(
        operation=f"restart_service:{service_name}",
        motivo="Reiniciar servicios combina stop/start y requiere confirmación explícita.",
        scope=[service_name],
        level="P3",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2: TRADING Y FINANZAS (5 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_trading_status() -> Dict:
    """Obtiene el estado del motor de trading."""
    try:
        motor_file = Path(r"C:\AI_VAULT\00_identity\financial_motor.py")
        trading_engine = Path(r"C:\AI_VAULT\00_identity\trading_engine.py")
        
        status: Dict[str, object] = {"motor_exists": motor_file.exists(), "trading_engine_exists": trading_engine.exists()}
        
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if capital_file.exists():
            try:
                data = json.loads(capital_file.read_text())
                status["capital_data"] = data
            except Exception as e:
                status["capital_error"] = f"Error leyendo estado: {e}"
        
        return {"success": True, "trading_available": motor_file.exists() and trading_engine.exists(), "status": status}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_capital_state() -> Dict:
    """Lee el estado actual del capital del sistema."""
    try:
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if not capital_file.exists():
            return {"success": False, "error": "Archivo de estado de capital no encontrado"}
        
        data = json.loads(capital_file.read_text())
        return {"success": True, "capital": data, "summary": {"initial": data.get("initial_capital", "N/A"), "cash": data.get("cash", "N/A"), "committed": data.get("committed", "N/A"), "drawdown": data.get("max_drawdown", "N/A"), "status": data.get("status", "N/A")}}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_brain_state() -> Dict:
    """Obtiene el estado actual de Brain."""
    try:
        brain_file = Path(r"C:\AI_VAULT\60_METRICS\brain_state.json")
        if not brain_file.exists():
            return {"success": False, "error": "Archivo de estado de Brain no encontrado"}
        
        data = json.loads(brain_file.read_text())
        return {"success": True, "brain_state": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_pocketoption_data(symbol: Optional[str] = None, amount: Optional[float] = None, duration: Optional[int] = None) -> Dict:
    """Obtiene datos en tiempo real del bridge de PocketOption."""
    try:
        bridge_files = [
            r"C:\AI_VAULT\tmp_agent\state\rooms\brain_binary_paper_pb04_demo_execution\browser_bridge_normalized_feed.json",
        ]
        
        for file_path in bridge_files:
            path = Path(file_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    return {"success": True, "source": str(path), "data": data}
                except Exception:
                    log.warning("Error reading PocketOption bridge file: %s", file_path)
                    continue
        
        return {"success": False, "error": "No se encontraron datos del bridge de PocketOption"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def execute_trade_paper(symbol: str, direction: str, amount: float = 10.0) -> Dict:
    """Ejecuta una orden de trading en modo paper (simulado)."""
    try:
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if capital_file.exists():
            capital_data = json.loads(capital_file.read_text())
            available = capital_data.get("cash")
            if available is None:
                available = capital_data.get("current_cash", 0)
            
            if available < amount:
                return {"success": False, "error": f"Capital insuficiente. Disponible: ${available}, Requerido: ${amount}", "status": "insufficient_funds"}
        
        # ── Route through the real strategy engine paper execution ──
        # The agent tool must NOT fabricate outcomes.  We delegate to
        # paper_execution.execute_paper_trade which uses market data or
        # deferred forward resolution.  If unavailable, report honestly.
        try:
            from brain_v9.trading.paper_execution import execute_paper_trade
            trade = execute_paper_trade(
                strategy={"strategy_id": "agent_manual", "family": "trend_following",
                           "venue": "internal", "preferred_symbol": symbol},
                signal={"direction": direction, "confidence": 0.5,
                         "symbol": symbol},
                feature={"last_vs_close_pct": 0.0, "bid_ask_imbalance": 0.0,
                          "payout_pct": 80.0, "price_available": True,
                          "last": None, "mid": None},
            )
            result = trade.get("result", "unknown")
            profit = trade.get("profit", 0.0)
        except Exception as imp_err:
            return {"success": False, "error": f"Paper execution not available: {imp_err}",
                    "status": "execution_unavailable"}

        return {"success": True, "trade": {"symbol": symbol, "direction": direction, "amount": amount, "result": result, "profit": profit, "mode": "paper", "timestamp": datetime.now().isoformat()}, "message": f"Trade {direction} en {symbol}: {result.upper()} (P&L: ${profit:.2f})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3: AUTONOMÍA Y ESTADO (3 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_autonomy_phase() -> Dict:
    """Obtiene la fase actual del sistema de autonomía."""
    try:
        autonomy_files = [
            r"C:\AI_VAULT\tmp_agent\state\autonomy_next_actions.json",
            r"C:\AI_VAULT\tmp_agent\state\meta_improvement_status_latest.json",
            r"C:\AI_VAULT\00_identity\autonomy_system\state\autonomy_state.json",
        ]
        
        for file_path in autonomy_files:
            path = Path(file_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    return {"success": True, "source": str(path), "phase": data.get("current_phase", "unknown"), "full_state": data}
                except Exception:
                    log.warning("Error reading autonomy state file: %s", file_path)
                    continue
        
        return {"success": True, "phase": "6.3", "description": "EJECUCIÓN_AUTONOMA", "note": "Sistema en fase de ejecución autónoma"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_rooms_status(limit: int = 10) -> Dict:
    """Obtiene el estado de las rooms de ejecución."""
    try:
        rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
        if not rooms_dir.exists():
            return {"success": False, "error": "Directorio de rooms no encontrado"}
        
        rooms = []
        for room_dir in sorted(rooms_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            if room_dir.is_dir():
                room_info = {"name": room_dir.name, "modified": datetime.fromtimestamp(room_dir.stat().st_mtime).isoformat()}
                
                for state_file in ["plan.json", "status.json"]:
                    state_path = room_dir / state_file
                    if state_path.exists():
                        try:
                            room_info[state_file.replace(".json", "")] = json.loads(state_path.read_text())
                        except Exception:
                            log.warning("Error reading room state file: %s/%s", room_dir.name, state_file)
                            room_info[state_file.replace(".json", "")] = "error_reading"
                
                rooms.append(room_info)
        
        return {"success": True, "total_rooms": len(list(rooms_dir.iterdir())), "rooms_shown": len(rooms), "rooms": rooms}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def read_state_json(file_path: str) -> Dict:
    """Lee cualquier archivo JSON de estado del sistema."""
    try:
        full_path = Path(file_path)
        ai_vault_root = Path(r"C:\AI_VAULT")
        
        try:
            full_path.relative_to(ai_vault_root)
        except ValueError:
            return {"success": False, "error": "Ruta fuera de AI_VAULT no permitida", "path": file_path}
        
        if not full_path.exists():
            return {"success": False, "error": "Archivo no encontrado", "path": str(full_path)}
        
        if not full_path.suffix == ".json":
            return {"success": False, "error": "Solo se permiten archivos .json", "path": str(full_path)}
        
        data = json.loads(full_path.read_text(encoding="utf-8"))
        return {"success": True, "path": str(full_path), "data": data}
    except Exception as e:
        return {"success": False, "error": str(e), "path": file_path}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4: DIAGNÓSTICO Y REPARACIÓN (2 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_diagnostic() -> Dict:
    """Ejecuta diagnóstico completo del ecosistema AI_VAULT."""
    diagnostic = {"timestamp": datetime.now().isoformat(), "checks": []}
    
    services_check = await check_service_status("all")
    diagnostic["checks"].append({"name": "Servicios principales", "result": services_check})
    
    capital_check = await get_capital_state()
    diagnostic["checks"].append({"name": "Estado de capital", "result": capital_check})
    
    brain_check = await get_brain_state()
    diagnostic["checks"].append({"name": "Estado de Brain", "result": brain_check})
    
    autonomy_check = await get_autonomy_phase()
    diagnostic["checks"].append({"name": "Fase de autonomía", "result": autonomy_check})
    
    trading_check = await get_trading_status()
    diagnostic["checks"].append({"name": "Motor de trading", "result": trading_check})
    
    successful = sum(1 for c in diagnostic["checks"] if c["result"].get("success", False))
    
    return {"success": True, "diagnostic": diagnostic, "summary": {"total_checks": len(diagnostic["checks"]), "successful": successful, "failed": len(diagnostic["checks"]) - successful, "status": "healthy" if successful == len(diagnostic["checks"]) else "degraded"}}


async def check_all_services() -> Dict:
    """Verificación completa de todos los servicios del ecosistema."""
    services_to_check = [
        {"name": "Brain V9", "port": 8090, "critical": True},
        {"name": "Brain Server", "port": 8000, "critical": False},
        {"name": "Advisor Server", "port": 8010, "critical": False},
    ]
    
    results = []
    critical_down = 0
    
    for svc in services_to_check:
        check = await check_port(svc["port"])
        is_running = check.get("status") == "en_uso"
        
        result = {"name": svc["name"], "port": svc["port"], "running": is_running, "critical": svc["critical"]}
        
        if svc["critical"] and not is_running:
            critical_down += 1
        
        results.append(result)
    
    return {"success": True, "overall_status": "critical" if critical_down > 0 else "healthy", "critical_services_down": critical_down, "services": results}


# Asegurar import de asyncio
import asyncio


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4 STAGE2: HERRAMIENTAS CANÓNICAS DE ANÁLISIS AVANZADO
# ═══════════════════════════════════════════════════════════════════════════════

async def get_context_edge_validation_live() -> Dict:
    """Returns the canonical context-edge validation snapshot (per setup_variant+symbol+timeframe)."""
    return await call_brain_api("/brain/strategy-engine/context-edge-validation")


async def get_learning_loop_live() -> Dict:
    """Returns the canonical learning loop snapshot with per-strategy decisions."""
    return await call_brain_api("/brain/strategy-engine/learning-loop")


async def get_active_catalog_live() -> Dict:
    """Returns the canonical active strategy catalog (operational strategies only)."""
    return await call_brain_api("/brain/strategy-engine/active-catalog")


async def get_post_trade_context_live() -> Dict:
    """Returns post-trade analysis with context dimensions (by_setup_variant, by_duration, by_payout)."""
    return await call_brain_api("/brain/strategy-engine/post-trade-analysis")


async def get_active_hypotheses_live() -> Dict:
    """Returns active hypotheses from the knowledge base with enriched validation plans."""
    return await call_brain_api("/brain/research/knowledge")


async def synthesize_edge_analysis() -> Dict:
    """Builds a consolidated analysis packet from canonical artifacts for LLM reasoning.

    Reads edge validation, learning loop, post-trade context, active catalog,
    and hypotheses. Returns a structured summary the LLM can use to generate
    prioritized recommendations without hallucinating over missing data.
    """
    try:
        from brain_v9.trading.context_edge_validation import read_context_edge_validation_snapshot
        from brain_v9.trading.learning_loop import read_learning_loop_snapshot
        from brain_v9.trading.post_trade_analysis import read_post_trade_analysis_snapshot
        from brain_v9.trading.active_strategy_catalog import read_active_strategy_catalog_snapshot

        context_edge = read_context_edge_validation_snapshot()
        learning = read_learning_loop_snapshot()
        post_trade = read_post_trade_analysis_snapshot()
        catalog = read_active_strategy_catalog_snapshot()

        # Extract actionable summaries (no raw data dumps)
        ce_summary = context_edge.get("summary", {})
        ll_summary = learning.get("summary", {})
        pt_summary = post_trade.get("summary", {})
        cat_summary = catalog.get("summary", {})

        # Learning loop items with decisions
        ll_items = learning.get("items", [])
        actionable_items = [
            {
                "strategy_id": item.get("strategy_id"),
                "state": item.get("catalog_state"),
                "decision": item.get("learning_decision"),
                "rationale": item.get("rationale"),
                "entries": item.get("entries_resolved"),
                "expectancy": item.get("expectancy"),
            }
            for item in ll_items
            if item.get("learning_decision") not in ("historical_only",)
        ]

        # Worst performing context dimensions
        worst_variants = sorted(
            post_trade.get("by_setup_variant", []),
            key=lambda x: x.get("avg_profit", 0),
        )[:3]
        worst_durations = sorted(
            post_trade.get("by_duration", []),
            key=lambda x: x.get("avg_profit", 0),
        )[:2]
        worst_payouts = sorted(
            post_trade.get("by_payout", []),
            key=lambda x: x.get("avg_profit", 0),
        )[:2]

        return {
            "success": True,
            "synthesis_type": "edge_analysis_consolidated",
            "context_edge_summary": ce_summary,
            "learning_loop_summary": ll_summary,
            "post_trade_summary": pt_summary,
            "active_catalog_summary": cat_summary,
            "actionable_learning_decisions": actionable_items,
            "worst_performing_variants": worst_variants,
            "worst_performing_durations": worst_durations,
            "worst_performing_payouts": worst_payouts,
            "top_learning_action": ll_summary.get("top_learning_action"),
            "allow_variant_generation": ll_summary.get("allow_variant_generation"),
            "variant_sources": ll_summary.get("variant_generation_sources", []),
            "recommendation_context": (
                "Use this data to prioritize the next concrete action. "
                "Do NOT invent statistics. Only reason over the numbers provided. "
                "Focus on: which strategy needs attention, which context loses money, "
                "what hypothesis should be tested next."
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# SELF-TEST & CHAT METRICS (for self-improvement impact measurement)
# ═══════════════════════════════════════════════════════════════════════════════

def run_self_test_tool(**kwargs) -> Dict:
    """Run the Brain self-test harness and return the score.

    No arguments required. Runs 15 curated queries against /chat
    and returns pass/fail/score/avg_latency.
    """
    try:
        from brain_v9.brain.self_test import run_self_test_sync
        result = run_self_test_sync(timeout_per_query=75)
        return {
            "success": True,
            "total": result["total"],
            "passed": result["passed"],
            "failed": result["failed"],
            "score": result["score"],
            "avg_latency_ms": result["avg_latency_ms"],
            "summary": (
                f"{result['passed']}/{result['total']} passed "
                f"({result['score']*100:.0f}%), "
                f"avg latency {result['avg_latency_ms']:.0f}ms"
            ),
            "failed_cases": [
                {"msg": c["msg"], "reason": c["reason"]}
                for c in result.get("cases", []) if not c["passed"]
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_chat_metrics(**kwargs) -> Dict:
    """Read the current chat quality metrics snapshot.

    No arguments required. Returns conversation counts, success rate,
    route breakdown, error types, and latency.
    """
    try:
        metrics_path = Path("C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json")
        if not metrics_path.exists():
            return {"success": True, "metrics": None, "note": "No chat metrics collected yet (file does not exist)."}
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        total = data.get("total_conversations", 0)
        success = data.get("success", 0)
        return {
            "success": True,
            "metrics": data,
            "success_rate": round(success / max(total, 1), 4),
            "total_conversations": total,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_self_test_history(**kwargs) -> Dict:
    """Read historical self-test scores to track quality over time.

    No arguments required. Returns last 50 self-test runs with
    timestamp, score, passed, total, avg_latency.
    """
    try:
        history_path = Path("C:/AI_VAULT/tmp_agent/state/brain_metrics/self_test_history.json")
        if not history_path.exists():
            return {"success": True, "history": [], "note": "No self-test history yet."}
        data = json.loads(history_path.read_text(encoding="utf-8"))
        return {
            "success": True,
            "runs": len(data),
            "history": data,
            "latest_score": data[-1]["score"] if data else None,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 6: AUTO-MEJORA AUTONOMA (self-improvement cycle)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_brain_tests(timeout_per_query: int = 75) -> Dict:
    """Ejecuta la bateria de self-tests del Brain V9 y devuelve resultados.

    Util para validar que cambios de codigo no rompen funcionalidad.
    Retorna: score, passed, failed, avg_latency, failed_cases.
    """
    try:
        from brain_v9.brain.self_test import run_self_test_sync
        result = run_self_test_sync(timeout_per_query=timeout_per_query)
        return {
            "success": True,
            "total": result["total"],
            "passed": result["passed"],
            "failed": result["failed"],
            "score": result["score"],
            "avg_latency_ms": result["avg_latency_ms"],
            "summary": (
                f"{result['passed']}/{result['total']} passed "
                f"({result['score']*100:.0f}%), "
                f"avg latency {result['avg_latency_ms']:.0f}ms"
            ),
            "failed_cases": [
                {"msg": c["msg"], "reason": c["reason"]}
                for c in result.get("cases", []) if not c["passed"]
            ],
            "all_passed": result["passed"] == result["total"],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def self_improve_cycle(
    file_path: str,
    old_text: str,
    new_text: str,
    objective: str = "",
    run_tests: bool = True,
    auto_promote: bool = False,
) -> Dict:
    """Ciclo completo de auto-mejora: edit -> validate -> test -> promote/rollback.

    Pipeline:
    1. Backup del archivo
    2. edit_file(path, old_text, new_text) — edicion quirurgica
    3. validate_python_change(path) — compila para verificar sintaxis
    4. run_brain_tests() — (opcional) corre self-tests
    5. Si todo OK y auto_promote=True: registra en ledger
    6. Si falla: rollback automatico desde backup

    Args:
        file_path: Ruta del archivo a modificar
        old_text: Texto exacto a reemplazar
        new_text: Texto de reemplazo
        objective: Descripcion del cambio
        run_tests: Correr self-tests despues de validar (default True)
        auto_promote: Registrar cambio en ledger si tests pasan (default False)

    Returns:
        Dict con resultado de cada fase y status final
    """
    result = {
        "file": file_path,
        "objective": objective,
        "phases": {},
        "success": False,
        "rolled_back": False,
    }

    # Phase 1: Backup
    try:
        backup_result = await backup_file(file_path)
        result["phases"]["backup"] = backup_result
        backup_path = str(backup_result.get("backup", ""))
    except Exception as exc:
        result["phases"]["backup"] = {"success": False, "error": str(exc)}
        result["error"] = "Fallo en backup — cambio abortado"
        return result

    # Phase 2: Edit
    try:
        edit_result = await edit_file(file_path, old_text, new_text)
        result["phases"]["edit"] = edit_result
        if not edit_result.get("success"):
            result["error"] = f"Fallo en edit: {edit_result.get('error')}"
            return result
    except Exception as exc:
        result["phases"]["edit"] = {"success": False, "error": str(exc)}
        result["error"] = f"Fallo en edit: {exc}"
        return result

    # Phase 3: Validate syntax
    try:
        validate_result = await validate_python_change([file_path])
        result["phases"]["validate"] = validate_result
        if not validate_result.get("success"):
            # Rollback
            log.warning("Validation failed, rolling back %s", file_path)
            _rollback_from_backup(file_path, backup_path)
            result["rolled_back"] = True
            result["error"] = f"Sintaxis invalida: {validate_result.get('stderr', '')[:200]}"
            return result
    except Exception as exc:
        _rollback_from_backup(file_path, backup_path)
        result["rolled_back"] = True
        result["phases"]["validate"] = {"success": False, "error": str(exc)}
        result["error"] = f"Fallo en validacion: {exc}"
        return result

    # Phase 4: Self-tests (optional)
    if run_tests:
        try:
            test_result = await run_brain_tests(timeout_per_query=60)
            result["phases"]["tests"] = test_result
            if not test_result.get("all_passed"):
                failed = test_result.get("failed_cases", [])
                log.warning("Tests failed after edit, rolling back %s", file_path)
                _rollback_from_backup(file_path, backup_path)
                result["rolled_back"] = True
                result["error"] = f"Tests fallaron: {len(failed)} casos"
                return result
        except Exception as exc:
            log.warning("Test execution error, rolling back %s", file_path)
            _rollback_from_backup(file_path, backup_path)
            result["rolled_back"] = True
            result["phases"]["tests"] = {"success": False, "error": str(exc)}
            result["error"] = f"Error ejecutando tests: {exc}"
            return result

    # Phase 5: Promote (optional)
    if auto_promote:
        try:
            staged = await create_staged_change([file_path], objective=objective, change_type="self_improvement")
            result["phases"]["staged"] = staged
            if staged.get("success") and staged.get("change_id"):
                promoted = await promote_staged_change(staged["change_id"])
                result["phases"]["promote"] = promoted
        except Exception as exc:
            result["phases"]["promote"] = {"success": False, "error": str(exc)}
            # Non-fatal: the edit succeeded, just ledger tracking failed

    result["success"] = True
    result["summary"] = f"Auto-mejora aplicada: {objective or file_path}"
    return result


def _rollback_from_backup(file_path: str, backup_path: str) -> None:
    """Restaura un archivo desde su backup."""
    try:
        bp = Path(backup_path)
        fp = Path(file_path)
        if bp.exists():
            fp.write_bytes(bp.read_bytes())
            log.info("Rolled back %s from %s", file_path, backup_path)
    except Exception as exc:
        log.error("Rollback failed for %s: %s", file_path, exc)


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 7: HERRAMIENTAS DESBLOQUEADAS (con governance gate)
# ═══════════════════════════════════════════════════════════════════════════════

async def kill_process(pid: Optional[int] = None, name: Optional[str] = None, force: bool = False, **kwargs) -> Dict:
    """Mata un proceso por PID o nombre.

    Requiere confirmacion via ExecutionGate (P2).
    Args:
        pid: Process ID a matar
        name: Nombre del proceso (e.g. "python.exe")
        force: Usar /F para forzar
    """
    if not pid and not name:
        return {"success": False, "error": "Necesitas especificar pid o name"}

    if pid:
        cmd = f"taskkill /PID {pid}"
    else:
        cmd = f'taskkill /IM "{name}"'
    if force:
        cmd += " /F"

    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("kill_process", {"pid": pid, "name": name, "force": force, "cmd": cmd})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }

    return await _run_internal_command(cmd, timeout=15)


async def install_package(package: str, upgrade: bool = False, **kwargs) -> Dict:
    """Instala un paquete Python via pip.

    Requiere confirmacion via ExecutionGate (P2).
    Args:
        package: Nombre del paquete (e.g. "requests", "pandas==2.0")
        upgrade: Usar --upgrade
    """
    cmd = f"pip install {package}"
    if upgrade:
        cmd += " --upgrade"

    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("install_package", {"package": package, "upgrade": upgrade})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }

    return await _run_internal_command(cmd, timeout=120)


async def run_python_script(script_path: str, args: str = "", timeout: int = 60, **kwargs) -> Dict:
    """Ejecuta un script Python arbitrario.

    Requiere confirmacion via ExecutionGate (P2).
    Args:
        script_path: Ruta al script .py
        args: Argumentos adicionales
        timeout: Timeout en segundos
    """
    p = _safe_path(script_path)
    if not p.exists():
        return {"success": False, "error": f"Script no existe: {p}"}
    if not p.suffix == ".py":
        return {"success": False, "error": f"Solo scripts .py: {p}"}

    cmd = f'python "{p}"'
    if args:
        cmd += f" {args}"

    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("run_python_script", {"script_path": str(p), "args": args})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }

    return await _run_internal_command(cmd, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 8: TRADING PIPELINE BRIDGE (5 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_strategy_scorecards() -> Dict:
    """Lee todos los scorecards de estrategia con governance state, métricas clave."""
    try:
        from brain_v9.trading.strategy_scorecard import read_scorecards
        data = read_scorecards()
        scorecards = data.get("scorecards", {})
        if not scorecards:
            return {"success": True, "count": 0, "strategies": [], "note": "No hay scorecards aún"}

        summary = []
        for sid, card in scorecards.items():
            summary.append({
                "strategy_id": sid,
                "venue": card.get("venue"),
                "governance_state": card.get("governance_state"),
                "wins": card.get("wins", 0),
                "losses": card.get("losses", 0),
                "entries_resolved": card.get("entries_resolved", 0),
                "entries_open": card.get("entries_open", 0),
                "win_rate": card.get("win_rate", 0.0),
                "expectancy": card.get("expectancy", 0.0),
                "net_pnl": card.get("net_pnl", 0.0),
                "profit_factor": card.get("profit_factor", 0.0),
                "freeze_reason": card.get("freeze_reason"),
            })

        return {
            "success": True,
            "count": len(summary),
            "schema_version": data.get("schema_version"),
            "updated_utc": data.get("updated_utc"),
            "strategies": summary,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def freeze_strategy(strategy_id: str = "", reason: str = "manual_agent_freeze", **kwargs) -> Dict:
    """Congela una estrategia (governance_state=frozen). Acción P2."""
    # Resilient: accept strategy_name as alias for strategy_id
    strategy_id = strategy_id or kwargs.get("strategy_name", "") or kwargs.get("name", "")
    if not strategy_id:
        return {"success": False, "error": "Falta strategy_id (o strategy_name)"}
    bypass_gate = kwargs.get("_bypass_gate", False)
    try:
        if not bypass_gate:
            from brain_v9.governance.execution_gate import get_gate
            gate = get_gate()
            decision = gate.check("freeze_strategy", {"strategy_id": strategy_id, "reason": reason})
            if not decision["allowed"]:
                return {
                    "success": False,
                    "error": decision["reason"],
                    "risk": decision["risk"],
                    "action": decision["action"],
                    "pending_id": decision.get("pending_id"),
                }

        from brain_v9.trading.strategy_scorecard import read_scorecards, SCORECARDS_PATH
        from brain_v9.core.state_io import write_json
        from datetime import timezone

        data = read_scorecards()
        scorecards = data.get("scorecards", {})

        if strategy_id not in scorecards:
            return {"success": False, "error": f"Estrategia '{strategy_id}' no encontrada en scorecards"}

        card = scorecards[strategy_id]
        current_state = card.get("governance_state", "unknown")
        if current_state == "frozen":
            return {"success": False, "error": f"Estrategia '{strategy_id}' ya está frozen", "current_state": current_state}
        if current_state == "retired":
            return {"success": False, "error": f"Estrategia '{strategy_id}' está retired, no se puede congelar"}

        card["governance_state"] = "frozen"
        card["promotion_state"] = "frozen"
        card["freeze_reason"] = reason
        card["freeze_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        card["freeze_recommended"] = True

        data["updated_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        write_json(SCORECARDS_PATH, data)

        log.info("freeze_strategy: %s frozen (reason=%s, prev_state=%s)", strategy_id, reason, current_state)
        return {
            "success": True,
            "strategy_id": strategy_id,
            "previous_state": current_state,
            "new_state": "frozen",
            "reason": reason,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def unfreeze_strategy(strategy_id: str = "", **kwargs) -> Dict:
    """Descongela una estrategia frozen (vuelve a paper_candidate). Acción P2."""
    # Resilient: accept strategy_name as alias for strategy_id
    strategy_id = strategy_id or kwargs.get("strategy_name", "") or kwargs.get("name", "")
    if not strategy_id:
        return {"success": False, "error": "Falta strategy_id (o strategy_name)"}
    bypass_gate = kwargs.get("_bypass_gate", False)
    try:
        if not bypass_gate:
            from brain_v9.governance.execution_gate import get_gate
            gate = get_gate()
            decision = gate.check("unfreeze_strategy", {"strategy_id": strategy_id})
            if not decision["allowed"]:
                return {
                    "success": False,
                    "error": decision["reason"],
                    "risk": decision["risk"],
                    "action": decision["action"],
                    "pending_id": decision.get("pending_id"),
                }

        from brain_v9.trading.strategy_scorecard import read_scorecards, SCORECARDS_PATH
        from brain_v9.core.state_io import write_json
        from datetime import timezone

        data = read_scorecards()
        scorecards = data.get("scorecards", {})

        if strategy_id not in scorecards:
            return {"success": False, "error": f"Estrategia '{strategy_id}' no encontrada en scorecards"}

        card = scorecards[strategy_id]
        current_state = card.get("governance_state", "unknown")
        if current_state != "frozen":
            return {"success": False, "error": f"Estrategia '{strategy_id}' no está frozen (state={current_state})"}

        card["governance_state"] = "paper_candidate"
        card["promotion_state"] = "paper_candidate"
        card.pop("freeze_reason", None)
        card.pop("freeze_utc", None)
        card["freeze_recommended"] = False
        card["manual_unfreeze_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        data["updated_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        write_json(SCORECARDS_PATH, data)

        log.info("unfreeze_strategy: %s unfrozen -> paper_candidate", strategy_id)
        return {
            "success": True,
            "strategy_id": strategy_id,
            "previous_state": "frozen",
            "new_state": "paper_candidate",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_execution_ledger(limit: int = 20) -> Dict:
    """Lee el historial reciente de ejecución paper de trades."""
    try:
        from brain_v9.trading.paper_execution import read_signal_paper_execution_ledger

        data = read_signal_paper_execution_ledger()
        entries = data.get("entries", [])
        if not entries:
            return {"success": True, "count": 0, "entries": [], "note": "Ledger vacío"}

        recent = entries[-limit:] if len(entries) > limit else entries

        summary = []
        for e in recent:
            summary.append({
                "entry_id": e.get("entry_id"),
                "strategy_id": e.get("strategy_id"),
                "venue": e.get("venue"),
                "symbol": e.get("symbol"),
                "direction": e.get("direction"),
                "status": e.get("status"),
                "pnl": e.get("pnl"),
                "outcome": e.get("outcome"),
                "opened_utc": e.get("opened_utc"),
                "resolved_utc": e.get("resolved_utc"),
            })

        return {
            "success": True,
            "total_entries": len(entries),
            "showing": len(summary),
            "entries": summary,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def trigger_autonomy_action(action_name: str = "", **kwargs) -> Dict:
    """Dispara una acción de autonomía del ACTION_MAP. Acción P2."""
    action_name = action_name or kwargs.get("action", "") or kwargs.get("name", "")
    if not action_name:
        return {"success": False, "error": "Falta action_name"}
    bypass_gate = kwargs.get("_bypass_gate", False)
    try:
        if not bypass_gate:
            from brain_v9.governance.execution_gate import get_gate
            gate = get_gate()
            decision = gate.check("trigger_autonomy_action", {"action_name": action_name})
            if not decision["allowed"]:
                return {
                    "success": False,
                    "error": decision["reason"],
                    "risk": decision["risk"],
                    "action": decision["action"],
                    "pending_id": decision.get("pending_id"),
                }

        from brain_v9.autonomy.action_executor import execute_action, ACTION_MAP

        if action_name not in ACTION_MAP:
            valid_actions = list(ACTION_MAP.keys())
            return {
                "success": False,
                "error": f"Acción '{action_name}' no existe en ACTION_MAP",
                "valid_actions": valid_actions,
            }

        result = await execute_action(action_name, force=False)
        return {
            "success": result.get("success", False),
            "action_name": action_name,
            "result": result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 9 WRAPPERS: Closed-Loop Trading (QC ingestion + IBKR execution + auto-promotion)
# ═══════════════════════════════════════════════════════════════════════════════


async def _tool_ingest_qc_results(**kwargs) -> Dict:
    """Ingesta resultados de backtests QC y actualiza scorecards.

    P0 (read+write interno) — no requiere gate porque es lectura de API
    externa + escritura a state files propios.
    """
    try:
        from brain_v9.trading.qc_results_ingester import ingest_qc_results
        result = await ingest_qc_results()
        return {
            "success": result.get("success", False),
            "summary": result.get("summary", ""),
            "projects_polled": result.get("projects_polled", 0),
            "new_backtests": result.get("new_backtests", 0),
            "new_strategies": result.get("new_strategies", 0),
            "updated_strategies": result.get("updated_strategies", 0),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        log.error("_tool_ingest_qc_results failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_place_paper_order(
    symbol: str = "",
    action: str = "",
    quantity: int = 0,
    order_type: str = "MKT",
    limit_price: float = 0.0,
    sec_type: str = "STK",
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    strategy_id: str = "",
    reason: str = "",
    **kwargs,
) -> Dict:
    """Coloca orden paper en IBKR Gateway (port 4002).

    P2 — requiere confirmacion via ExecutionGate.
    """
    if not symbol:
        return {"success": False, "error": "Falta 'symbol' (e.g. 'SPY')"}
    if not action or action.upper() not in ("BUY", "SELL"):
        return {"success": False, "error": "Falta 'action' — debe ser 'BUY' o 'SELL'"}
    if quantity <= 0:
        return {"success": False, "error": "Falta 'quantity' (debe ser > 0)"}

    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("place_paper_order", {
            "symbol": symbol, "action": action, "quantity": quantity,
            "order_type": order_type, "sec_type": sec_type,
            "strategy_id": strategy_id, "reason": reason,
        })
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }

    try:
        from brain_v9.trading.ibkr_order_executor import place_paper_order_async
        result = await place_paper_order_async(
            symbol=symbol,
            action=action.upper(),
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            sec_type=sec_type,
            expiry=expiry,
            strike=strike,
            right=right,
            strategy_id=strategy_id,
            reason=reason,
        )
        return result
    except Exception as e:
        log.error("_tool_place_paper_order failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_cancel_paper_order(order_id: int = 0, **kwargs) -> Dict:
    """Cancela orden paper abierta en IBKR Gateway.

    P2 — requiere confirmacion via ExecutionGate.
    """
    if not order_id:
        return {"success": False, "error": "Falta 'order_id' (int)"}

    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("cancel_paper_order", {"order_id": order_id})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }

    try:
        from brain_v9.trading.ibkr_order_executor import cancel_paper_order_async
        result = await cancel_paper_order_async(order_id=order_id)
        return result
    except Exception as e:
        log.error("_tool_cancel_paper_order failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_get_ibkr_positions(**kwargs) -> Dict:
    """Lee posiciones paper actuales desde IBKR Gateway. P0 — lectura."""
    try:
        from brain_v9.trading.ibkr_order_executor import get_positions_async
        result = await get_positions_async()
        return result
    except Exception as e:
        log.error("_tool_get_ibkr_positions failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_get_ibkr_open_orders(**kwargs) -> Dict:
    """Lee órdenes paper abiertas desde IBKR Gateway. P0 — lectura."""
    try:
        from brain_v9.trading.ibkr_order_executor import get_open_orders_async
        result = await get_open_orders_async()
        return result
    except Exception as e:
        log.error("_tool_get_ibkr_open_orders failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_get_ibkr_account(**kwargs) -> Dict:
    """Lee resumen de cuenta paper IBKR. P0 — lectura."""
    try:
        from brain_v9.trading.ibkr_order_executor import get_account_summary_async
        result = await get_account_summary_async()
        return result
    except Exception as e:
        log.error("_tool_get_ibkr_account failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_auto_promote(**kwargs) -> Dict:
    """Promueve estrategias promote_candidate → live_paper.

    P2 — requiere confirmacion via ExecutionGate.
    Delega a auto_promote_to_ibkr_paper() en action_executor.
    """
    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("auto_promote_strategies", {})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }

    try:
        from brain_v9.autonomy.action_executor import auto_promote_to_ibkr_paper
        result = await auto_promote_to_ibkr_paper()
        return result
    except Exception as e:
        log.error("_tool_auto_promote failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_scan_ibkr_signals(**kwargs) -> Dict:
    """Escanea estrategias live_paper, evalúa condiciones y despacha órdenes.

    P2 — requiere confirmacion via ExecutionGate (ejecuta órdenes).
    """
    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("scan_ibkr_signals", {})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }
    try:
        from brain_v9.trading.ibkr_signal_engine import scan_and_execute
        result = await scan_and_execute()
        return result
    except Exception as e:
        log.error("_tool_scan_ibkr_signals failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_poll_ibkr_performance(**kwargs) -> Dict:
    """Polling de posiciones IBKR → actualiza P&L en scorecards. P0 — lectura+write interno."""
    try:
        from brain_v9.trading.ibkr_performance_tracker import poll_ibkr_performance
        result = await poll_ibkr_performance()
        return result
    except Exception as e:
        log.error("_tool_poll_ibkr_performance failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_iterate_strategy(strategy_id: str = "", **kwargs) -> Dict:
    """Analiza una estrategia underperformer, identifica causas, propone y aplica ajustes.

    P2 — modifica código en QC + lanza re-backtest.
    """
    strategy_id = strategy_id or kwargs.get("name", "") or kwargs.get("sid", "")
    if not strategy_id:
        return {"success": False, "error": "Falta 'strategy_id'"}

    bypass_gate = kwargs.get("_bypass_gate", False)
    if not bypass_gate:
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        decision = gate.check("iterate_strategy", {"strategy_id": strategy_id})
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "risk": decision["risk"],
                "action": decision["action"],
                "pending_id": decision.get("pending_id"),
            }
    try:
        from brain_v9.trading.qc_iteration_engine import iterate_strategy
        result = await iterate_strategy(strategy_id)
        return result
    except Exception as e:
        log.error("_tool_iterate_strategy failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_analyze_strategy(strategy_id: str = "", **kwargs) -> Dict:
    """Analiza performance de una estrategia con LLM. P0 — solo lectura y análisis."""
    strategy_id = strategy_id or kwargs.get("name", "") or kwargs.get("sid", "")
    if not strategy_id:
        return {"success": False, "error": "Falta 'strategy_id'"}
    try:
        from brain_v9.trading.qc_iteration_engine import analyze_strategy_performance
        result = await analyze_strategy_performance(strategy_id)
        return result
    except Exception as e:
        log.error("_tool_analyze_strategy failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_get_signal_log(**kwargs) -> Dict:
    """Lee el log de señales recientes del signal engine. P0 — lectura."""
    try:
        from brain_v9.trading.ibkr_signal_engine import get_signal_log
        limit = int(kwargs.get("limit", 50))
        return {"success": True, **get_signal_log(limit)}
    except Exception as e:
        log.error("_tool_get_signal_log failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_get_iteration_history(strategy_id: str = "", **kwargs) -> Dict:
    """Lee historial de iteraciones de estrategias. P0 — lectura."""
    strategy_id = strategy_id or kwargs.get("name", "")
    try:
        from brain_v9.trading.qc_iteration_engine import get_iteration_history
        return {"success": True, **get_iteration_history(strategy_id or None)}
    except Exception as e:
        log.error("_tool_get_iteration_history failed: %s", e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# QC LIVE MONITORING + ANALYSIS TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

async def _tool_analyze_qc_live(days: int = 7, **kwargs) -> Dict:
    """Ejecuta análisis completo de degradación del QC Live deployment.
    P0 — lectura y análisis. Detecta tendencia de equity, drawdown vs backtest,
    win rate, Sharpe, volatilidad. Genera sugerencias auto-aplicables si hay
    degradación dentro de los límites permitidos (< 20%)."""
    try:
        from brain_v9.trading.qc_live_analyzer import run_analysis_cycle
        result = run_analysis_cycle()
        status = result.get("status", "unknown")
        if status == "not_deployed":
            return {"success": True, "message": "QC Live no está deployed — no hay datos para analizar."}
        if status == "insufficient_data":
            return {"success": True, "message": f"Datos insuficientes: {result.get('snapshots_count', 0)}/{result.get('required', 12)} snapshots.", **result}
        analysis = result.get("analysis", {})
        health = analysis.get("health", {})
        suggestions = analysis.get("suggestions", [])
        return {
            "success": True,
            "health": health.get("overall", "unknown"),
            "equity_trend": analysis.get("equity_trend", {}).get("direction", "unknown"),
            "snapshots_analyzed": analysis.get("snapshots_analyzed", 0),
            "suggestions_count": len(suggestions),
            "suggestions": suggestions,
            "drawdown": analysis.get("drawdown_analysis", {}),
            "win_rate": analysis.get("win_rate_analysis", {}),
            "sharpe": analysis.get("sharpe_analysis", {}),
        }
    except Exception as e:
        log.error("_tool_analyze_qc_live failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_get_qc_live_status(**kwargs) -> Dict:
    """Lee el estado actual del deployment QC Live (equity, posiciones, métricas, alertas).
    P0 — solo lectura."""
    try:
        from brain_v9.trading.qc_live_monitor import get_live_state
        state = get_live_state()
        return {"success": True, **state}
    except Exception as e:
        log.error("_tool_get_qc_live_status failed: %s", e)
        return {"success": False, "error": str(e)}


async def _tool_register_qc_live_deploy(**kwargs) -> Dict:
    """Registra un deploy live hecho manualmente (via QC web UI).
    Requiere deploy_id. Activa el monitor de polling automáticamente.
    P1 — escritura de estado."""
    try:
        deploy_id = kwargs.get("deploy_id", "")
        project_id = int(kwargs.get("project_id", 29490680))
        node_id = kwargs.get("node_id", "LN-64d4787830461ee45574254f643f69b3")
        strategy_name = kwargs.get("strategy_name", "V10.13b (Determined Sky Blue Galago)")
        if not deploy_id:
            return {"success": False, "error": "deploy_id is required"}
        from brain_v9.trading.qc_live_monitor import get_live_state, set_live_deployed
        state = get_live_state()
        if state.get("deployed"):
            return {"success": False, "error": "already_deployed", "existing_deploy_id": state.get("deploy_id")}
        set_live_deployed(deploy_id=deploy_id, project_id=project_id, node_id=node_id, strategy_name=strategy_name)
        return {"success": True, "deploy_id": deploy_id, "message": "External deploy registered"}
    except Exception as e:
        log.error("_tool_register_qc_live_deploy failed: %s", e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK INTROSPECTION (native, stdlib-only — no external deps required)
# Added 2026-04-30: addresses gap detected in network_scan capability test.
# Brain previously assumed 192.168.1.x; real network was 172.20.10.0/28.
# ═══════════════════════════════════════════════════════════════════════════════

def _list_local_interfaces() -> List[Dict[str, Any]]:
    """Lista interfaces de red locales con IP/netmask. Usa psutil si disponible,
    si no cae a stdlib (socket.gethostbyname_ex) que da menos info pero funciona."""
    interfaces: List[Dict[str, Any]] = []
    try:
        import psutil  # type: ignore
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, addr_list in addrs.items():
            up = bool(stats.get(name) and stats[name].isup)
            for a in addr_list:
                # AF_INET = IPv4
                if getattr(a, "family", None) == socket.AF_INET:
                    interfaces.append({
                        "name": name,
                        "ip": a.address,
                        "netmask": a.netmask,
                        "broadcast": getattr(a, "broadcast", None),
                        "is_up": up,
                        "is_loopback": a.address.startswith("127."),
                    })
    except Exception:
        # Fallback stdlib: solo IP primaria
        try:
            host = socket.gethostname()
            _, _, ips = socket.gethostbyname_ex(host)
            for ip in ips:
                interfaces.append({
                    "name": "primary",
                    "ip": ip,
                    "netmask": None,
                    "broadcast": None,
                    "is_up": True,
                    "is_loopback": ip.startswith("127."),
                })
        except Exception:
            pass
    return interfaces


def _ip_to_cidr(ip: str, netmask: Optional[str]) -> Optional[str]:
    """Calcula CIDR (e.g. '172.20.10.8/28') usando ipaddress stdlib."""
    if not ip or not netmask:
        return None
    try:
        import ipaddress
        net = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
        return str(net)
    except Exception:
        return None


def _interface_priority(item: Dict[str, Any]) -> int:
    name = str(item.get("name") or "").lower()
    ip = str(item.get("ip") or "")
    if item.get("is_loopback") or not item.get("is_up"):
        return -100
    score = 0
    if "wi-fi" in name or "wifi" in name or "wlan" in name:
        score += 50
    if "ethernet" in name and "vethernet" not in name:
        score += 30
    if "vethernet" in name or "wsl" in name or "hyper-v" in name:
        score -= 40
    if "docker" in name or "virtual" in name or "vbox" in name or "vmware" in name:
        score -= 30
    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
        score += 5
    return score


async def detect_local_network() -> Dict:
    """
    Detecta la red local real del sistema (interfaces, IPs, CIDR, gateway).
    Usa stdlib + psutil opcional. NO requiere instalación de nmap/scapy.
    Resuelve el gap de "el brain asume 192.168.1.x sin verificar".
    """
    try:
        ifaces = _list_local_interfaces()
        non_loopback = [i for i in ifaces if not i["is_loopback"] and i["is_up"]]
        primary = max(non_loopback, key=_interface_priority) if non_loopback else None
        cidr = _ip_to_cidr(primary["ip"], primary["netmask"]) if primary else None

        # Gateway via netstat (Windows) / ip route (Linux)
        gateway = None
        try:
            if os.name == "nt":
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1).NextHop"],
                    capture_output=True, text=True, timeout=5,
                )
                gateway = (out.stdout or "").strip() or None
            else:
                out = subprocess.run(["ip", "route", "show", "default"],
                                     capture_output=True, text=True, timeout=5)
                line = (out.stdout or "").strip().split("\n")[0]
                parts = line.split()
                if "via" in parts:
                    gateway = parts[parts.index("via") + 1]
        except Exception as e:
            gateway = None

        return {
            "success": True,
            "primary_ip": primary["ip"] if primary else None,
            "primary_cidr": cidr,
            "gateway": gateway,
            "interfaces": ifaces,
            "interface_count": len(ifaces),
            "active_count": len(non_loopback),
            "platform": os.name,
            "note": "Native introspection (stdlib+psutil). No nmap/scapy required.",
        }
    except Exception as e:
        log.error("detect_local_network failed: %s", e)
        return {"success": False, "error": str(e)}


async def scan_local_network(cidr: Optional[str] = None, timeout: float = 0.5,
                             max_hosts: int = 64, auto_chunk: bool = True,
                             max_total_hosts: int = 1024, **kwargs) -> Dict:
    """
    Ping/TCP sweep de la red local (sin nmap). Usa socket.connect_ex puerto 445/80/22.
    Si no se pasa CIDR, usa el detectado por detect_local_network().

    R20: si len(hosts) > max_hosts y auto_chunk=True (default), trocea
    automaticamente y agrega resultados (limitado por max_total_hosts).
    Pasa auto_chunk=False para forzar el comportamiento legacy (early return).

    R25: acepta aliases del LLM para 'cidr': network, target, subnet, range, ip_range.
    """
    try:
        import ipaddress
        auto_tokens = {"auto", "current", "local", "wifi", "lan", "default"}
        if isinstance(cidr, str) and cidr.strip().lower() in auto_tokens:
            cidr = None
        # R25: alias resolution (el LLM tiende a usar 'network=' en lugar de 'cidr=')
        if not cidr:
            for alias in ("network", "target", "subnet", "range", "ip_range", "net"):
                v = kwargs.get(alias)
                if v:
                    candidate = str(v).strip()
                    if candidate.lower() in auto_tokens:
                        cidr = None
                        break
                    cidr = candidate
                    break
        if not cidr:
            det = await detect_local_network()
            cidr = det.get("primary_cidr")
            if not cidr:
                return {"success": False, "error": "no_local_cidr_detected"}

        net = ipaddress.IPv4Network(cidr, strict=False)
        hosts = list(net.hosts())
        probe_ports = [445, 139, 80, 22, 53]

        # R20: helper sincronico para probar 1 host (ejecutado via to_thread)
        def _probe_one(ip_str: str) -> Optional[Dict[str, Any]]:
            open_ports: List[int] = []
            for port in probe_ports:
                s = None
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    if s.connect_ex((ip_str, port)) == 0:
                        open_ports.append(port)
                except Exception:
                    pass
                finally:
                    if s is not None:
                        try:
                            s.close()
                        except Exception:
                            pass
            if open_ports:
                return {"ip": ip_str, "open_ports": open_ports}
            return None

        async def _probe_chunk(chunk_hosts: List[Any]) -> List[Dict[str, Any]]:
            tasks = [asyncio.to_thread(_probe_one, str(ip)) for ip in chunk_hosts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results if isinstance(r, dict)]

        # R20: legacy behavior si auto_chunk=False
        if len(hosts) > max_hosts and not auto_chunk:
            return {
                "success": False,
                "error": f"network_too_large (hosts={len(hosts)} > max_hosts={max_hosts}). "
                         f"Pasa auto_chunk=True o max_hosts=N explicito si quieres barrer mas.",
                "cidr": str(net),
                "host_count": len(hosts),
            }

        # R20: cap absoluto para no barrer /8 enteros
        truncated = False
        if len(hosts) > max_total_hosts:
            hosts = hosts[:max_total_hosts]
            truncated = True

        live: List[Dict[str, Any]] = []
        chunks = 0
        # Trocea en chunks de max_hosts y procesa concurrentemente dentro de cada chunk
        for i in range(0, len(hosts), max_hosts):
            chunk = hosts[i:i + max_hosts]
            live.extend(await _probe_chunk(chunk))
            chunks += 1

        return {
            "success": True,
            "cidr": str(net),
            "hosts_probed": len(hosts),
            "live_hosts": live,
            "live_count": len(live),
            "ports_probed": probe_ports,
            "chunks": chunks,
            "auto_chunked": chunks > 1,
            "truncated": truncated,
            "method": "tcp_connect (stdlib, no nmap, async chunked)",
        }
    except Exception as e:
        log.error("scan_local_network failed: %s", e)
        return {"success": False, "error": str(e)}


def build_standard_executor() -> ToolExecutor:
    """Crea un ToolExecutor con todas las herramientas estándar registradas."""
    ex = ToolExecutor()

    # Filesystem
    ex.register("read_file",       read_file,       "Lee un archivo de texto",                    "filesystem")
    ex.register("write_file",      write_file,      "Escribe contenido a un archivo",             "filesystem")
    ex.register("edit_file",       edit_file,       "Edicion quirurgica: reemplaza old_text por new_text (unica ocurrencia, con backup)", "filesystem")
    ex.register("backup_file",     backup_file,     "Crea un backup con timestamp de un archivo", "filesystem")
    ex.register("create_staged_change", create_staged_change, "Crea un cambio en staging con metadata y ledger", "filesystem")
    ex.register("list_directory",  list_directory,  "Lista el contenido de un directorio",        "filesystem")
    ex.register("search_files",    search_files,    "Busca archivos por nombre o contenido",      "filesystem")
    ex.register("grep_codebase",   grep_codebase,   "Busca texto en todo el codebase brain_v9 (case-insensitive, con contexto)", "code")

    # Código
    ex.register("analyze_python",  analyze_python,  "Analiza estructura de un archivo Python",    "code")
    ex.register("find_in_code",    find_in_code,    "Busca un término en código fuente",          "code")
    ex.register("check_syntax",    check_syntax,    "Verifica sintaxis de un archivo Python",     "code")
    ex.register("validate_python_change", validate_python_change, "Compila cambios Python para validar que no rompen sintaxis/import basico", "code")
    ex.register("validate_staged_change", validate_staged_change, "Valida un cambio staged y actualiza su metadata", "code")

    # Sistema
    ex.register("get_system_info", get_system_info, "Obtiene CPU, memoria y disco actuales",      "system")
    ex.register("get_gpu_status", get_gpu_status, "Obtiene VRAM/uso GPU via nvidia-smi si esta disponible", "system")
    ex.register("get_technical_introspection", get_technical_introspection, "Snapshot tecnico del Brain: proceso, VRAM, codigo y capacidades", "system")
    ex.register("run_command",     run_command,     "Ejecuta un comando de shell (lectura)",      "system")
    ex.register("run_powershell",  run_powershell,  "Ejecuta script PowerShell via -File (sin double-parse cmd.exe). args: file_path o script (ASCII), args, cwd, timeout", "system")

    # Memoria semantica / metacognicion visible
    ex.register("semantic_memory_status", semantic_memory_status, "Estado de la memoria semantica persistente", "memory")
    ex.register("semantic_memory_search", semantic_memory_search, "Busca contexto en memoria semantica vectorial local", "memory")
    ex.register("semantic_memory_ingest", semantic_memory_ingest, "Inserta texto en memoria semantica persistente", "memory")
    ex.register("semantic_memory_ingest_session", semantic_memory_ingest_session, "Importa memoria de sesion existente a memoria semantica", "memory")
    ex.register("get_metacognition_status", get_metacognition_status, "Estado de metacognicion visible y auditoria de confianza", "self_eval")
    ex.register("audit_claims", audit_claims, "Audita riesgo de alucinacion de afirmaciones con evidencia opcional", "self_eval")
    ex.register("request_clarification", request_clarification, "Solicita aclaracion estructurada cuando falta objetivo o contexto", "self_eval")

    # HTTP / Network
    ex.register("check_http_service", check_http_service, "Verifica si un servicio HTTP responde", "network")
    ex.register("detect_local_network", detect_local_network, "Detecta red local real (interfaces, IP, CIDR, gateway) usando stdlib+psutil. Sin nmap.", "network")
    ex.register("scan_local_network", scan_local_network, "Sweep TCP de la red local (puertos comunes) sin nmap, usando stdlib.", "network")
    # NOTA: check_port_status removida - usar check_port (más completa)
    ex.register("diagnose_dashboard", diagnose_dashboard, "Diagnostico del dashboard integrado en Brain V9 :8090/ui", "network")

    # Windows / Servicios Brain
    ex.register("check_port",           check_port,           "Verifica qué proceso usa un puerto en Windows",           "system")
    ex.register("list_processes",       list_processes,       "Lista procesos corriendo, opcionalmente filtrados",        "system")
    ex.register("check_url",            check_url,            "Verifica si una URL/servicio web responde",               "system")
    ex.register("find_dashboard_files", find_dashboard_files, "Busca todos los archivos de dashboard en AI_VAULT",       "brain")
    
    # Dashboard API
    ex.register("get_dashboard_data",   get_dashboard_data,   "Consulta datos del dashboard autonomía (integrado en :8090) - endpoints: status, roadmap/v2, roadmap/bl, pocketoption/data", "brain")
    ex.register("get_live_autonomy_status", get_live_autonomy_status, "Lee el estado vivo de autonomia/utility/strategy desde el runtime actual", "brain")
    ex.register("execute_top_action_live", execute_top_action_live, "Ejecuta la top_action actual en el Brain vivo", "brain")
    ex.register("get_strategy_engine_live", get_strategy_engine_live, "Lee el resumen vivo del strategy engine actual", "brain")
    ex.register("get_edge_validation_live", get_edge_validation_live, "Lee el snapshot canónico de edge validation del Brain vivo", "brain")
    ex.register("get_strategy_ranking_v2_live", get_strategy_ranking_v2_live, "Lee el ranking-v2 canónico del Brain vivo", "brain")
    ex.register("get_pipeline_integrity_live", get_pipeline_integrity_live, "Lee la integridad canónica del pipeline de trading del Brain vivo", "brain")
    ex.register("get_risk_status_live", get_risk_status_live, "Lee el contrato canónico de riesgo financiero del Brain vivo", "brain")
    ex.register("get_governance_health_live", get_governance_health_live, "Lee la salud canónica de gobernanza y composición de capas del Brain vivo", "brain")
    ex.register("get_post_trade_hypotheses_live", get_post_trade_hypotheses_live, "Lee la síntesis canónica post-trade e hipótesis del Brain vivo", "brain")
    ex.register("get_security_posture_live", get_security_posture_live, "Lee la postura canónica de seguridad del Brain vivo", "brain")
    ex.register("get_change_control_live", get_change_control_live, "Lee el scorecard canónico de control de cambios del Brain vivo", "brain")
    ex.register("get_control_layer_live", get_control_layer_live, "Lee el estado canónico del control layer / kill switch del Brain vivo", "brain")
    ex.register("get_meta_governance_live", get_meta_governance_live, "Lee el estado canónico de meta-gobernanza y prioridades del Brain vivo", "brain")
    ex.register("get_session_memory_live", get_session_memory_live, "Lee la memoria canónica de sesión del Brain vivo", "brain")
    ex.register("refresh_strategy_engine_live", refresh_strategy_engine_live, "Refresca snapshots del strategy engine actual", "brain")
    ex.register("execute_strategy_candidate_live", execute_strategy_candidate_live, "Ejecuta un strategy candidate concreto en el runtime vivo", "brain")
    
    # Iniciar servicios
    ex.register("start_dashboard",      start_dashboard,      "Dashboard integrado en Brain V9 :8090/ui (port 8070 retired)",  "brain")
    ex.register("start_brain_server", start_brain_server,   "Inicia el servidor Brain Chat V9",                        "brain")
    ex.register("restart_brain_v9_safe", restart_brain_v9_safe, "Reinicia Brain V9 con helper externo y artifact de health", "brain")
    ex.register("promote_staged_change", promote_staged_change, "Promueve un cambio staged con gate y helper de reinicio", "brain")
    ex.register("rollback_staged_change", rollback_staged_change, "Restaura backups de un cambio staged", "brain")
    ex.register("get_self_improvement_ledger", get_self_improvement_ledger, "Lee el ledger canónico de automejora", "brain")
    ex.register("list_recent_brain_changes", list_recent_brain_changes, "Lista TODAS las mejoras recientes del Brain (ledger formal + ediciones directas a archivos del codigo). USA ESTA tool para preguntas como 'mejoras recientes', 'que cambio', 'ultimas modificaciones'.", "brain")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 1: SERVICIOS DEL ECOSISTEMA AI_VAULT (8 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("start_brain_v7", start_brain_v7, "Inicia Brain Chat V7/V8 legacy en puerto 8095", "ecosystem")
    ex.register("start_dashboard_autonomy", start_dashboard_autonomy, "Dashboard de Autonomia integrado en Brain V9 :8090/ui (port 8070 retired)", "ecosystem")
    ex.register("start_brain_server_legacy", start_brain_server_legacy, "Inicia Brain Server legacy en puerto 8000", "ecosystem")
    ex.register("start_advisor_server", start_advisor_server, "Inicia Advisor Server en puerto 8010", "ecosystem")
    ex.register("check_service_status", check_service_status, "Verifica estado de servicios del ecosistema", "ecosystem")
    ex.register("stop_service", stop_service, "Detiene un servicio del ecosistema por nombre", "ecosystem")
    ex.register("restart_service", restart_service, "Reinicia un servicio del ecosistema", "ecosystem")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 2: TRADING Y FINANZAS (5 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("get_trading_status", get_trading_status, "Obtiene estado del motor de trading", "trading")
    ex.register("get_capital_state", get_capital_state, "Lee estado actual del capital del sistema", "trading")
    ex.register("get_brain_state", get_brain_state, "Obtiene estado actual de Brain", "trading")
    ex.register("get_pocketoption_data", get_pocketoption_data, "Obtiene datos en tiempo real del bridge de PocketOption", "trading")
    ex.register("execute_trade_paper", execute_trade_paper, "Ejecuta orden de trading en modo paper (simulado)", "trading")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 3: AUTONOMÍA Y ESTADO (3 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("get_autonomy_phase", get_autonomy_phase, "Obtiene fase actual del sistema de autonomía", "autonomy")
    ex.register("get_rooms_status", get_rooms_status, "Obtiene estado de las rooms de ejecución", "autonomy")
    ex.register("read_state_json", read_state_json, "Lee cualquier archivo JSON de estado del sistema", "autonomy")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 4: DIAGNÓSTICO Y REPARACIÓN (2 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("run_diagnostic", run_diagnostic, "Ejecuta diagnóstico completo del ecosistema AI_VAULT", "diagnostic")
    ex.register("check_all_services", check_all_services, "Verificación completa de todos los servicios", "diagnostic")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 4 STAGE2: HERRAMIENTAS CANÓNICAS DE ANÁLISIS AVANZADO (6 herramientas)
    # Edge por contexto, learning loop, catálogo activo, post-trade por contexto,
    # hipótesis activas, y síntesis LLM sobre datos canónicos.
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("get_context_edge_validation_live", get_context_edge_validation_live, "Lee el snapshot canónico de validación de edge POR CONTEXTO (setup_variant+symbol+timeframe) del Brain vivo", "brain")
    ex.register("get_learning_loop_live", get_learning_loop_live, "Lee el snapshot canónico del learning loop: decisiones de aprendizaje por estrategia (audit, continue, tighten, forward_validate, generate_variant)", "brain")
    ex.register("get_active_catalog_live", get_active_catalog_live, "Lee el catálogo activo canónico: solo estrategias operativas por venue, sin archived/refuted/frozen", "brain")
    ex.register("get_post_trade_context_live", get_post_trade_context_live, "Lee el análisis post-trade con dimensiones de contexto: by_setup_variant, by_duration, by_payout", "brain")
    ex.register("get_active_hypotheses_live", get_active_hypotheses_live, "Lee las hipótesis activas del knowledge base con validation_plan ejecutable", "brain")
    ex.register("synthesize_edge_analysis", synthesize_edge_analysis, "Genera un análisis LLM consolidado sobre edge, learning loop, hipótesis y post-trade para priorizar siguiente acción", "brain")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 5: AUTO-EVALUACIÓN (self-test, chat metrics, quality history)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("run_self_test",        run_self_test_tool,    "Ejecuta el self-test: 15 queries contra /chat, devuelve score/passed/failed/latency",  "self_eval")
    ex.register("get_chat_metrics",     get_chat_metrics,      "Lee las métricas de calidad del chat: conversations, success_rate, routes, errors",    "self_eval")
    ex.register("get_self_test_history", get_self_test_history, "Lee el historial de self-tests para ver evolución de calidad en el tiempo",           "self_eval")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 6: AUTO-MEJORA AUTONOMA
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("run_brain_tests",     run_brain_tests,       "Corre la bateria completa de self-tests del Brain V9 y devuelve score/passed/failed",   "self_improvement")
    ex.register("self_improve_cycle",  self_improve_cycle,    "Ciclo completo: edit_file -> validate -> test -> promote/rollback automatico",          "self_improvement")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 7: HERRAMIENTAS DESBLOQUEADAS (governance-gated, P2)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("kill_process",       kill_process,          "Mata un proceso por PID o nombre (P2, requiere confirmacion)",                          "self_improvement")
    ex.register("install_package",    install_package,       "Instala paquete Python via pip (P2, requiere confirmacion)",                            "self_improvement")
    ex.register("run_python_script",  run_python_script,     "Ejecuta un script Python (P2, requiere confirmacion)",                                 "self_improvement")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 8: TRADING PIPELINE BRIDGE (5 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("get_strategy_scorecards",  get_strategy_scorecards,  "Lee todos los scorecards de estrategia con governance, métricas y PnL",     "trading")
    ex.register("freeze_strategy",          freeze_strategy,          "Congela una estrategia (P2, requiere confirmacion)",                         "trading")
    ex.register("unfreeze_strategy",        unfreeze_strategy,        "Descongela una estrategia frozen (P2, requiere confirmacion)",               "trading")
    ex.register("get_execution_ledger",     get_execution_ledger,     "Lee historial reciente de ejecución paper de trades",                       "trading")
    ex.register("trigger_autonomy_action",  trigger_autonomy_action,  "Dispara una acción de autonomía del ACTION_MAP (P2, requiere confirmacion)","autonomy")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 9: CLOSED-LOOP TRADING (QC ingestion + IBKR execution + auto-promotion)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("ingest_qc_results",     _tool_ingest_qc_results,     "Ingesta resultados de backtests QC → actualiza scorecards (P0, read+write)", "trading")
    ex.register("place_paper_order",     _tool_place_paper_order,     "Coloca orden paper en IBKR Gateway (P2, requiere confirmacion)",             "trading")
    ex.register("cancel_paper_order",    _tool_cancel_paper_order,    "Cancela orden paper abierta en IBKR (P2, requiere confirmacion)",            "trading")
    ex.register("get_ibkr_positions",    _tool_get_ibkr_positions,    "Lee posiciones paper actuales desde IBKR Gateway (P0, lectura)",             "trading")
    ex.register("get_ibkr_open_orders",  _tool_get_ibkr_open_orders,  "Lee órdenes paper abiertas desde IBKR Gateway (P0, lectura)",               "trading")
    ex.register("get_ibkr_account",      _tool_get_ibkr_account,      "Lee resumen de cuenta paper IBKR (P0, lectura)",                            "trading")
    ex.register("auto_promote_strategies", _tool_auto_promote,        "Promueve estrategias promote_candidate → live_paper (P2, requiere confirm.)","trading")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 9b: CLOSED-LOOP ENGINE (signal scan + P&L tracking + iteration)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("scan_ibkr_signals",    _tool_scan_ibkr_signals,     "Escanea señales live_paper → despacha paper orders IBKR (P2)",               "trading")
    ex.register("poll_ibkr_performance",_tool_poll_ibkr_performance, "Poll posiciones IBKR → actualiza P&L scorecards (P0)",                       "trading")
    ex.register("iterate_strategy",     _tool_iterate_strategy,      "Analiza+ajusta estrategia underperformer via LLM (P2, modifica QC)",         "trading")
    ex.register("analyze_strategy",     _tool_analyze_strategy,      "Análisis LLM de performance de una estrategia (P0, solo lectura)",           "trading")
    ex.register("get_signal_log",       _tool_get_signal_log,        "Lee log reciente de señales del signal engine (P0)",                         "trading")
    ex.register("get_iteration_history",_tool_get_iteration_history,  "Lee historial de iteraciones QC de estrategias (P0)",                       "trading")

    # ═══════════════════════════════════════════════════════════════════════════════
    # QC LIVE MONITORING (LOOP 2)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("analyze_qc_live",      _tool_analyze_qc_live,       "Análisis degradación QC Live: equity, DD, WR, Sharpe vs backtest (P0)",      "trading")
    ex.register("get_qc_live_status",   _tool_get_qc_live_status,    "Lee estado actual del deployment QC Live (equity, posiciones, alertas) (P0)", "trading")
    ex.register("register_qc_live_deploy", _tool_register_qc_live_deploy, "Registra deploy live manual (web UI) — requiere deploy_id (P1)", "trading")

    try:
        from brain.capability_governor import get_capability_governor

        get_capability_governor().register_runtime_tools(ex.list_tools())
    except Exception as exc:
        log.debug("Capability governor inventory sync unavailable: %s", exc)

    log.info("ToolExecutor listo: %d tools", len(ex.list_tools()))
    return ex
