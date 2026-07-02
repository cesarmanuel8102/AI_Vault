from __future__ import annotations
import re
from typing import Any, Dict, List

from .mandatory_tools import parse_mandatory_tool_requests

PLANNER_CLASSES = [
    "repo_audit", "code_search", "endpoint_probe", "memory_question", "dashboard_diagnosis",
    "provider_diagnosis", "frontend_diagnosis", "smoke_test", "documentation_task",
    "safe_patch_dry_run", "approval_required_write", "general_reasoning", "mandatory_multitool",
    "explicit_tool_request", "autonomy_diagnosis", "recent_changes_diagnosis",
    "teacher_codex_search", "memory_structure_diagnosis", "semantic_memory_status",
    "promotion_queue_status", "trace_inspect", "capability_registry_read",
    "financial_autonomy_diagnosis", "evidence_required_diagnosis",
    "brain_self_knowledge_lookup",
]

# Explicit tool request patterns - if user names a tool, schedule it directly
EXPLICIT_TOOL_PATTERNS = {
    # Direct verb + tool name (highest priority)
    r"(?:programa|solicita|solicitar|usa|usar|ejecuta|ejecutar|verifica|verificar|schedule|run|use|execute)\s+([a-z_][a-z0-9_]*)" : r"\1",
    # Spanish explicit tool requests with scheduling verb
    r"(?:programa|solicita|solicitar|usa|usar|ejecuta|ejecutar|verifica|verificar)\s+(?:al\s+)?(?:planner\s+)?(?:que\s+)?(?:programe|schedule)\s+([a-z_][a-z0-9_]*)" : r"\1",
    # Tool main/complement patterns
    r"(?:tool\s+principal|tool\s+main)\s*[:\-]?\s*([a-z_][a-z0-9_]*)" : r"\1",
    r"(?:complementada\s+con|complemented\s+with)\s+([a-z_][a-z0-9_]*)" : r"\1",
    # English explicit tool requests with action verb + tool type
    r"(?:schedule|run|use|execute)\s+(?:the\s+)?([a-z_][a-z0-9_]*)\s+(?:tool|check|test)" : r"\1",
}

GENERIC_TOOL_WORDS = {
    "tool", "tools", "herramienta", "herramientas", "check", "checks",
    "test", "tests", "prueba", "pruebas", "evidencia", "evidence",
}

# Diagnostic phrase mappings - when user describes a symptom, map to diagnostic tools
DIAGNOSTIC_PHRASES = {
    # Autonomy heartbeat diagnostic
    "autonomy_heartbeat": {
        "triggers": [
            r"heartbeat\s+(?:is\s+)?stale",
            r"heartbeat\s+(?:is\s+)?old",
            r"verify\s+autonomy\s+process",
            r"autonomy\s+process",
            r"autonomy\s+heartbeat",
            r"heartbeat\s+stale",
            r"heartbeat\s+is\s+stale",
            r"verificar\s+(?:el\s+)?proceso\s+de\s+autonomia",
            r"proceso\s+de\s+autonomia",
            r"heartbeat\s+de\s+autonomia",
            r"heartbeat\s+antiguo",
            r"heartbeat\s+viejo",
        ],
        "tools": [
            ("get_live_autonomy_status", {"check": "autonomy_heartbeat"}),
            ("check_service_status", {"check": "autonomy_services"}),
            ("get_autonomy_phase", {"check": "autonomy_phase"}),
            ("repo_status_read", {}),
        ],
        "unavailable_notes": "get_live_autonomy_status, check_service_status, get_autonomy_phase are diagnostic endpoints that may not be available as direct tools",
    },
    # Recent brain/kernel changes
    "recent_changes": {
        "triggers": [
            r"(?:ultimos|últimos|recent|last)\s+(?:cambios|changes)",
            r"cambios\s+(?:en\s+)?(?:el\s+)?(?:kernel|agente|brain)",
            r"recent\s+(?:brain|kernel|agent)\s+changes",
            r"changes\s+in\s+(?:the\s+)?(?:brain|kernel|agent)",
            r"ultimos\s+cambios\s+en\s+el\s+agente",
            r"cambios\s+recientes",
            r"recent\s+changes\s+in\s+agent",
        ],
        "tools": [
            ("list_recent_brain_changes", {"limit": 10}),
            ("repo_history_read", {"path": "tmp_agent/brain_v9", "limit": 10}),
            ("repo_status_read", {}),
            ("grep_search", {"pattern": "agent_kernel_v2|NativeAgentRuntimeV2|planner.py|tool_gateway.py", "glob": "*.py"}),
        ],
        "unavailable_notes": "list_recent_brain_changes may not exist as direct tool; falls back to repo_history_read + repo_status_read + grep_search",
    },
    # Git log/diff phrases
    "git_history": {
        "triggers": [
            r"git\s+log",
            r"git\s+history", 
            r"git\s+diff",
            r"historial\s+de\s+git",
            r"diff\s+de\s+git",
            r"log\s+de\s+git",
            r"(?:ultimos|últimos|recent)\s+commits",
            r"commits\s+recientes",
            r"archivos\s+modificados",
            r"modified\s+files",
        ],
        "tools": [
            ("repo_history_read", {"path": "tmp_agent/brain_v9", "limit": 10}),
            ("repo_diff_read", {"path": "tmp_agent/brain_v9"}),
            ("repo_status_read", {}),
        ],
        "unavailable_notes": "repo_history_read and repo_diff_read provide safe read-only git log/diff equivalents",
    },
}

EVIDENCE_ACTION_RE = re.compile(
    r"\b(audit|audita|auditar|review|revisa|revisar|inspect|inspecciona|diagnose|"
    r"diagnostica|explain|explica|explicar|how|como|cómo|why|por\s+que|por\s+qué|"
    r"status|estado|evidence|evidencia|verify|verifica|confirm|confirma|valora|"
    r"valorar|demuestra|prove|"
    # Repair P1 (front-brain-agent-v2-intent-floor-and-identity-preamble-repair-01):
    # extended action verbs to match intent_classifier EVIDENCE_ACTION_TERMS.
    r"buscar|search|donde|dónde|where|primero|first|identidad|identity|eres|"
    r"cual|cuál|which|quien|quién|backend|ejecutando|running|usas|use|haces|"
    r"hiciste|debes|should|must|gaps|brechas|roadmap|puedes|capaz|capaces|"
    r"listar|list|run|corre|ejecuta|ejecutar|smoke|readonly|read-only|"
    # Fix B (front-brain-agent-v2-identity-guard-and-intent-floor-widen-02):
    # mirror of intent_classifier reconciliation / validation / source-citation
    # additions so planner's evidence gate stays consistent with classifier.
    r"reconcilia|reconciliar|reconcile|valida|validate|"
    r"fuente|fuentes|realmente|really)\b",
    re.IGNORECASE,
)

EVIDENCE_DOMAIN_RE = re.compile(
    r"\b(brain|agent|agente|agent\s+v2|langgraph|kernel|runtime|repo|repository|"
    r"repositorio|dashboard|chat|ui|memory|memoria|semantic|faiss|trace|traza|"
    r"tool|tools|herramientas?|financial_autonomy|financial\s+autonomy|"
    r"autonom(?:ia|ía)\s+financiera|broker_execution_enabled|real_money_enabled|"
    r"promotion\s+queue|cola\s+de\s+promoci(?:o|ó)n|candidate|candidato|"
    r"governance|gobernanza|provider|kimi|ollama|finalizer|planner|selector|"
    r"router|arquitectura|architecture|autodesarrollo|self-development|"
    r"autoconocimiento|capacidades|capabilities|"
    # Repair P2 (front-brain-agent-v2-intent-floor-and-identity-preamble-repair-01):
    # extended Brain-adjacent domain terms to match intent_classifier EVIDENCE_DOMAIN_TERMS.
    r"trading|ibkr|broker|self-knowledge|self\s+knowledge|pruebas|tests|ci|"
    r"smoke_test_readonly|backend|"
    # Fix B (front-brain-agent-v2-identity-guard-and-intent-floor-widen-02):
    # mirror of intent_classifier HEAD / learning-proposals / promotion_queue
    # domain additions so planner's evidence gate matches classifier.
    r"head|learning\s+proposals|learning_proposals|proposals|"
    r"promotion_queue)\b",
    re.IGNORECASE,
)


def _requires_generic_evidence(goal: str) -> bool:
    """Return True when a prompt should not be answered without tools.

    This is the planner counterpart to intent_classifier's evidence policy.
    It keeps root-cause behavior consistent even when planner classification is
    called directly by tests or runtimes.
    """
    g = goal or ""
    if not EVIDENCE_DOMAIN_RE.search(g):
        return False
    if EVIDENCE_ACTION_RE.search(g):
        return True
    return bool(re.search(
        r"langgraph|financial_autonomy|broker_execution_enabled|real_money_enabled|"
        r"promotion\s+queue|cola\s+de\s+promoci(?:o|ó)n|trace|traza|semantic|faiss|"
        r"autodesarrollo|self-development|autoconocimiento|"
        # Repair P3 (front-brain-agent-v2-intent-floor-and-identity-preamble-repair-01):
        # extended always-evidence regex to match intent_classifier always_evidence set.
        r"brain|agent|agente|memoria|memory|dashboard|kernel|runtime|backend|"
        r"trading|ibkr|broker|smoke_test_readonly|roadmap|"
        # Fix B (front-brain-agent-v2-identity-guard-and-intent-floor-widen-02):
        # HEAD / learning-proposals / promotion_queue always-evidence anchors.
        r"head|proposals|learning\s+proposals|learning_proposals|promotion_queue",
        g,
        re.IGNORECASE,
    ))


def _detect_explicit_tool_requests(goal: str) -> List[Dict[str, Any]]:
    """Detect if user explicitly names a tool. Returns list of tool requests."""
    import re
    requests = []
    seen_tools = set()
    for pattern, tool_name_group in EXPLICIT_TOOL_PATTERNS.items():
        for match in re.finditer(pattern, goal, re.IGNORECASE):
            tool_name = match.group(1).strip().lower()
            if tool_name in GENERIC_TOOL_WORDS:
                continue
            if tool_name and len(tool_name) > 2 and tool_name not in seen_tools:
                seen_tools.add(tool_name)
                requests.append({
                    "tool_name": tool_name,
                    "confidence": "high",
                    "source": "explicit_request",
                    "matched_text": match.group(0),
                })
    return requests


def _detect_diagnostic_phrases(goal: str) -> List[Dict[str, Any]]:
    """Detect diagnostic phrases and map to recommended tools."""
    import re
    diagnostics = []
    g = goal.lower()
    
    for diag_name, diag_config in DIAGNOSTIC_PHRASES.items():
        triggered = False
        for trigger in diag_config["triggers"]:
            if re.search(trigger, g):
                triggered = True
                break
        if triggered:
            diagnostics.append({
                "diagnosis": diag_name,
                "tools": diag_config["tools"],
                "unavailable_notes": diag_config.get("unavailable_notes", ""),
            })
    
    return diagnostics


def classify_goal(goal: str, mode: str = "read_only") -> str:
    g = (goal or "").lower()
    
    # Check for explicit tool requests first (highest priority)
    explicit = _detect_explicit_tool_requests(goal)
    if explicit:
        return "explicit_tool_request"
    
    # Check diagnostic phrases before generic keyword classification
    diagnostics = _detect_diagnostic_phrases(goal)
    if diagnostics:
        # Return specific diagnostic classification if exactly one
        if len(diagnostics) == 1:
            return diagnostics[0]["diagnosis"]
        # If multiple, use explicit_tool_request to schedule all
        return "explicit_tool_request"
    
    # Prevent "programa X tool" from being misclassified as safe_patch_dry_run
    if re.search(r"(?:programa|solicita|solicitar|usa|ejecuta|verifica)\s+(?:al\s+)?(?:planner\s+)?(?:que\s+)?(?:programe|programe|schedule|run|use|execute)\s+([a-z_]+)", g):
        return "explicit_tool_request"

    # Specific read-only evidence classifications must run before generic
    # dry-run/memory/autonomy keywords so diagnostic prompts do not become
    # patch previews or direct answers.
    if any(x in g for x in [
        "financial_autonomy", "financial autonomy", "autonomía financiera",
        "autonomia financiera", "broker_execution_enabled", "real_money_enabled",
        "sistema financiero autónomo", "sistema financiero autonomo",
    ]):
        return "financial_autonomy_diagnosis"
    if any(x in g for x in [
        "self-development", "self development", "autodesarrollo", "auto desarrollo",
        "capacidades actuales", "current capabilities", "audita tus capacidades",
        "auditar capacidades", "autoconocimiento", "self knowledge",
    ]):
        return "brain_self_knowledge_lookup"
    if any(x in g for x in [
        "trace inspect", "inspect trace", "inspecciona trace", "lee trace",
        "trace reciente", "recent trace", "traza reciente", "traza",
        "herramientas reales", "solo respuesta", "tools actually executed",
    ]):
        return "trace_inspect"
    if any(x in g for x in ["memory structure", "estructura de memoria", "como esta estructurada", "que falta para que funcione", "persistent memory structure", "estructurada la memoria"]):
        return "memory_structure_diagnosis"
    if any(x in g for x in ["semantic memory status", "estado de la memoria semantica", "faiss status", "indice faiss", "estado faiss"]):
        return "semantic_memory_status"
    if any(x in g for x in ["promotion queue", "cola de promocion", "candidates pending", "review queue", "cola de revision"]):
        return "promotion_queue_status"
    if any(x in g for x in ["capability registry", "registro de capacidades", "list capabilities", "que capacidades", "lee capacidades"]):
        return "capability_registry_read"
    if _requires_generic_evidence(goal):
        return "evidence_required_diagnosis"
    
    if any(x in g for x in [".env", "apply patch", "commit", "push", "write tool", "blocked write"]):
        return "approval_required_write"
    # Only classify as safe_patch_dry_run if actual patch/diff is requested, not tool scheduling
    if any(x in g for x in ["patch", "diff", "dry-run", "dry run"]) and not any(x in g for x in ["schedule", "programa", "solicita", "tool principal"]):
        return "safe_patch_dry_run"
    if any(x in g for x in ["provider", "kimi", "ollama", "model"]):
        return "provider_diagnosis"
    if any(x in g for x in ["git status", "repository", "repo ", " repo", "clean", "head", "branch"]):
        return "repo_audit"
    if any(x in g for x in ["where", "find", "grep", "implemented", "route is", "/chat", "/v2/agent"]):
        return "code_search"
    if any(x in g for x in ["8091", "8092", "endpoint", "health", "probe", "live"]):
        return "endpoint_probe"
    if any(x in g for x in ["memory", "faiss", "semantic", "governance", "learned"]):
        return "memory_question"
    if "dashboard" in g:
        return "dashboard_diagnosis"
    if any(x in g for x in ["frontend", "ui", "panel"]):
        return "frontend_diagnosis"
    if any(x in g for x in ["smoke", "pytest", "test"]):
        return "smoke_test"
    if any(x in g for x in ["doc", "runbook", "documentation"]):
        return "documentation_task"
    
    # Check for autonomy-related but not matched by explicit diagnostics
    # NOTE: kept for backward compat but demoted; primary routing is now evidence-driven
    if any(x in g for x in ["autonomy", "heartbeat", "promotion queue"]):
        return "autonomy_diagnosis"
    
    # Check for recent changes but not matched by explicit diagnostics
    if any(x in g for x in ["changes", "cambios", "commits", "history", "log", "diff"]):
        return "recent_changes_diagnosis"
    
    # New evidence intent classifications (maps from intent_classifier.py new intents)
    if any(x in g for x in ["teacher mode", "modo teacher", "codex teacher", "maestro codex", "aprendizaje guiado", "teacher codex"]):
        return "teacher_codex_search"
    return "general_reasoning"


def build_plan(goal: str, mode: str = "read_only") -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Build plan. Returns (classification, plan_list, metadata_dict)."""
    # Check for mandatory multi-tool requests first
    mandatory = parse_mandatory_tool_requests(goal)
    plan: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {"requested_checks": [], "scheduled_tools": [], "executed_tools": []}

    def add(step_id, kind, title, tool, args, requested_by_user=False):
        entry = {
            "step_id": step_id,
            "kind": kind,
            "title": title,
            "status": "planned",
            "tool_name": tool,
            "input": args,
        }
        if requested_by_user:
            entry["requested_by_user"] = True
            entry["expected"] = "ok"
        plan.append(entry)
        if tool and tool not in metadata["scheduled_tools"]:
            metadata["scheduled_tools"].append(tool)

    if mandatory["mandatory_detected"]:
        classification = "mandatory_multitool"
        add("plan", "plan", f"Classify goal as {classification} (mandatory multi-tool)", None, {})
        # Add each requested check as a dedicated step
        for check in mandatory["requested_checks"]:
            # Skip final answer obligations - they're not tool calls
            if check.get("is_final_answer_requirement"):
                metadata.setdefault("final_answer_obligations", []).append(check)
                continue
            add(
                check.get("check_id", f"mandatory_{len(plan)}"),
                "tool",
                check.get("description", f"Run {check.get('tool_name', 'unknown')}"),
                check.get("tool_name"),
                check.get("input", {}),
                requested_by_user=True,
            )
            metadata["requested_checks"].append(check)
        # Always add a final consolidation step
        add("mandatory_summary", "summary", "Consolidate mandatory multi-tool results", None, {})
        return classification, plan, metadata

    # Check for explicit tool requests and diagnostic phrases
    explicit_requests = _detect_explicit_tool_requests(goal)
    diagnostics = _detect_diagnostic_phrases(goal)
    
    if explicit_requests or diagnostics:
        classification = "explicit_tool_request" if explicit_requests else (diagnostics[0]["diagnosis"] if diagnostics else "general_reasoning")
        add("plan", "plan", f"Classify goal as {classification} (explicit tool/diagnostic request)", None, {})
        
        # Build plan from explicit requests and diagnostics
        explicit_plan = _build_explicit_tool_plan(goal, explicit_requests, diagnostics, metadata)
        plan.extend(explicit_plan)
        
        # Add final summary
        add("explicit_summary", "summary", "Consolidate explicit tool request results", None, {})
        return classification, plan, metadata

    # Fallback to keyword-driven classification
    classification = classify_goal(goal, mode)
    add("plan", "plan", f"Classify goal as {classification}", None, {})

    if classification in {
        "brain_self_knowledge_lookup",
        "capability_registry_read",
        "financial_autonomy_diagnosis",
        "memory_structure_diagnosis",
        "semantic_memory_status",
        "promotion_queue_status",
        "trace_inspect",
        "dashboard_diagnosis",
        "evidence_required_diagnosis",
    }:
        add("self_knowledge", "tool", "Read canonical Brain self-knowledge source map", "brain_self_knowledge_lookup", {"query": goal, "top_k": 4})

    if classification in {"memory_question", "provider_diagnosis", "dashboard_diagnosis", "general_reasoning"}:
        add("retrieve", "memory", "Read-only semantic retrieval", "semantic_retrieve", {"query": goal, "top_k": 4})
    if classification in {"repo_audit", "dashboard_diagnosis", "provider_diagnosis", "general_reasoning"}:
        add("repo_status", "tool", "Read repository status", "repo_status_read", {})
    if classification in {"code_search", "dashboard_diagnosis", "provider_diagnosis", "frontend_diagnosis", "documentation_task"}:
        pattern = "/chat|v2/agent|agent_v2|kimi|provider|dashboard|finalizer" if classification != "documentation_task" else "Agent V2|finalizer|tool gateway|self maintenance"
        glob = "*.py" if classification != "documentation_task" else "*.md"
        add("grep_search", "tool", "Search relevant code/docs", "grep_search", {"pattern": pattern, "glob": glob})
    if classification in {"code_search", "provider_diagnosis"}:
        add("file_read", "tool", "Read Agent V2 runtime file", "file_read", {"path": "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py"})
    if classification in {"endpoint_probe", "dashboard_diagnosis", "frontend_diagnosis", "provider_diagnosis"}:
        add("probe_8091_status", "tool", "Probe Agent V2 status", "route_probe", {"url": "http://127.0.0.1:8091/v2/agent/status"})
        add("probe_8091_capabilities", "tool", "Probe Agent V2 capabilities", "route_probe", {"url": "http://127.0.0.1:8091/v2/agent/capabilities"})
    if classification in {"dashboard_diagnosis", "frontend_diagnosis"}:
        add("probe_8092_dashboard", "tool", "Probe dashboard status", "route_probe", {"url": "http://127.0.0.1:8092/brain-dashboard/status"})
    if classification == "smoke_test":
        add("smoke", "tool", "Run allowlisted smoke test", "smoke_test_readonly", {"target": "tests/smoke/smoke_front_brain_agent_v2_total_operational_excellence_closeout_01.py"})
    if classification == "teacher_codex_search":
        add("codex_search", "tool", "Search for teacher/codex mode references", "repo_file_search", {"pattern": "teacher|codex|aprendizaje guiado", "glob": "*.py"})
        add("semantic_codex", "memory", "Retrieve semantic memory for codex/teacher", "semantic_retrieve", {"query": "codex teacher mode guided learning", "top_k": 3})
    if classification == "memory_structure_diagnosis":
        add("memory_inspect", "tool", "Inspect memory structure", "memory_structure_inspect", {})
        add("semantic_status", "tool", "Check semantic memory status", "semantic_memory_status", {})
        add("repo_status", "tool", "Read repository status", "repo_status_read", {})
    if classification == "semantic_memory_status":
        add("semantic_status", "tool", "Check semantic memory status", "semantic_memory_status", {})
    if classification == "promotion_queue_status":
        add("promotion_status", "tool", "Check promotion queue status", "promotion_queue_status", {})
    if classification == "trace_inspect":
        add("repo_status", "tool", "Read repository status", "repo_status_read", {})
        add("repo_history", "tool", "Read recent commit history", "repo_history_read", {"path": "tmp_agent/brain_v9", "limit": 5})
        add("trace_search", "tool", "Search trace/tool evidence wiring", "repo_file_search", {"pattern": "tool_evidence|tool_result|trace|tools_executed|evidence_sources", "glob": "*.py"})
        add("trace_runtime_read", "tool", "Read Agent V2 trace/runtime adapter", "repo_file_read", {"path": "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py", "max_bytes": 8000})
    if classification == "capability_registry_read":
        add("capability_read", "tool", "Read capability registry", "capability_registry_read", {})
        add("capability_search", "tool", "Search self-development capability wiring", "repo_file_search", {"pattern": "capability|autodesarrollo|self_improvement|agent_kernel_v2|langgraph", "glob": "*.py"})
        add("capability_history", "tool", "Read recent agent capability commits", "repo_history_read", {"path": "tmp_agent/brain_v9/core/agent_kernel_v2", "limit": 8})
    if classification == "brain_self_knowledge_lookup":
        add("capability_read", "tool", "Read capability registry", "capability_registry_read", {})
        add("brain_evidence_search", "tool", "Search Brain Agent V2 evidence", "repo_file_search", {"pattern": "Agent V2|LangGraphParityRuntimeV2|capability|dashboard|semantic_memory|financial_autonomy|promotion_queue|tool_gateway", "glob": "*.py"})
        add("semantic_context", "memory", "Retrieve semantic context for Brain self-knowledge", "semantic_retrieve", {"query": goal, "top_k": 3})
    if classification == "financial_autonomy_diagnosis":
        add("financial_search", "tool", "Search financial autonomy safety flags", "repo_file_search", {"pattern": "financial_autonomy|FinancialAutonomy|broker_execution_enabled|real_money_enabled|dry_run", "glob": "*.py"})
        add("financial_init", "tool", "Read financial_autonomy package contract", "repo_file_read", {"path": "financial_autonomy/__init__.py", "max_bytes": 4000})
        add("financial_bridge", "tool", "Read financial autonomy bridge", "repo_file_read", {"path": "financial_autonomy/bridge/financial_autonomy_bridge.py", "max_bytes": 8000})
        add("financial_smoke", "tool", "Read dry-run safety smoke", "repo_file_read", {"path": "tests/smoke/test_front_financial_autonomy_compile_contract_10.py", "max_bytes": 8000})
        add("financial_memory", "memory", "Retrieve financial autonomy memory", "semantic_retrieve", {"query": "financial_autonomy dry-run broker_execution_enabled real_money_enabled autonomous financial system", "top_k": 3})
    if classification == "evidence_required_diagnosis":
        add("repo_status", "tool", "Read repository status", "repo_status_read", {})
        add("brain_evidence_search", "tool", "Search Brain Agent V2 evidence", "repo_file_search", {"pattern": "LangGraphParityRuntimeV2|Agent V2|agent_kernel_v2|capability|finalizer|planner|tool_results|evidence_sources|financial_autonomy|semantic_memory|dashboard", "glob": "*.py"})
        add("runtime_read", "tool", "Read LangGraph parity runtime", "repo_file_read", {"path": "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py", "max_bytes": 10000})
        add("capability_read", "tool", "Read capability registry", "capability_registry_read", {})
        add("semantic_context", "memory", "Retrieve semantic context for internal Brain question", "semantic_retrieve", {"query": goal, "top_k": 4})
    if classification == "safe_patch_dry_run":
        add("patch_dry_run", "tool", "Prepare patch preview only", "file_patch_dry_run", {"goal": goal})
    if classification == "approval_required_write":
        add("blocked_write", "tool", "Verify write gate", "file_patch_apply_approval_required", {"path": "README.md", "patch": "approval gate probe"})
    if len(plan) == 1:
        add("retrieve", "memory", "Read-only semantic retrieval", "semantic_retrieve", {"query": goal, "top_k": 3})

    return classification, plan, metadata


def _resolve_tool(tool_name: str) -> tuple[str, Dict[str, Any], str]:
    """Map requested tool name to available canonical tool. Returns (canonical_name, args, note)."""
    import re
    t = tool_name.strip().lower()
    
    # Direct mappings for tools that exist
    direct_map = {
        "repo_status_read": ("repo_status_read", {}, ""),
        "grep_search": ("grep_search", {"pattern": "agent", "glob": "*.py"}, ""),
        "file_read": ("file_read", {"path": "README.md"}, "path needs to be specified"),
        "route_probe": ("route_probe", {"url": "http://127.0.0.1:8091/health"}, "url needs to be specified"),
        "semantic_retrieve": ("semantic_retrieve", {"query": "agent", "top_k": 3}, "query needs to be specified"),
        "smoke_test_readonly": ("smoke_test_readonly", {"target": "tests/smoke"}, "target needs to be specified"),
        "file_patch_dry_run": ("file_patch_dry_run", {}, ""),
        "file_patch_apply_approval_required": ("file_patch_apply_approval_required", {}, ""),
        "git_commit_approval_required": ("git_commit_approval_required", {}, ""),
        "repo_file_search": ("repo_file_search", {"pattern": "agent", "glob": "*.py"}, "pattern needs to be specified"),
        "repo_file_read": ("repo_file_read", {"path": "README.md"}, "path needs to be specified"),
        "memory_structure_inspect": ("memory_structure_inspect", {}, ""),
        "semantic_memory_status": ("semantic_memory_status", {}, ""),
        "promotion_queue_status": ("promotion_queue_status", {}, ""),
        "capability_registry_read": ("capability_registry_read", {}, ""),
        "brain_self_knowledge_lookup": ("brain_self_knowledge_lookup", {"query": "Brain self knowledge", "top_k": 4}, "query can be specified"),
    }
    
    if t in direct_map:
        return direct_map[t]
    
    # Map missing diagnostic tools to safe equivalents
    # list_recent_brain_changes -> repo_history_read + grep_search + repo_status_read
    if t in ["list_recent_brain_changes", "recent_brain_changes", "brain_changes", "kernel_changes"]:
        return ("repo_history_read", {"path": "tmp_agent/brain_v9", "limit": 10}, "list_recent_brain_changes not available; using repo_history_read as safe equivalent")
    
    # get_live_autonomy_status -> route_probe to autonomy endpoint + repo_status_read
    if t in ["get_live_autonomy_status", "autonomy_status", "live_autonomy"]:
        return ("route_probe", {"url": "http://127.0.0.1:8091/brain/autonomy/status"}, "get_live_autonomy_status not available; probing autonomy endpoint if exists")
    
    # check_service_status -> route_probe to health endpoint
    if t in ["check_service_status", "service_status", "service_check"]:
        return ("route_probe", {"url": "http://127.0.0.1:8091/health"}, "check_service_status not available; using route_probe to health endpoint")
    
    # get_autonomy_phase -> semantic_retrieve about autonomy phase
    if t in ["get_autonomy_phase", "autonomy_phase", "phase"]:
        return ("semantic_retrieve", {"query": "autonomy phase current state", "top_k": 3}, "get_autonomy_phase not available; using semantic_retrieve as fallback")
    
    # repo_history_read -> repo_status_read + grep_search (git log equivalent)
    if t in ["repo_history_read", "git_log", "git_history", "history_read"]:
        return ("repo_status_read", {}, "repo_history_read not available; using repo_status_read + manual git log via grep")
    
    # repo_diff_read -> repo_status_read (diff info from git status)
    if t in ["repo_diff_read", "git_diff", "diff_read"]:
        return ("repo_status_read", {}, "repo_diff_read not available; using repo_status_read for change summary")
    
    # git log --oneline equivalent
    if re.search(r"git\s+log", t):
        return ("repo_status_read", {}, "git log not available as direct tool; repo_status_read provides HEAD info")
    
    # git diff equivalent
    if re.search(r"git\s+diff", t):
        return ("repo_status_read", {}, "git diff not available as direct tool; repo_status_read provides change summary")
    
    # read_file equivalent
    if t in ["read_file", "file_read", "leer_archivo", "readfile"]:
        return ("file_read", {"path": "README.md"}, "file_read available; path needs to be specified")
    
    # Default: unknown tool
    return ("", {}, f"Tool '{tool_name}' not found in registry and has no safe equivalent")


def _build_explicit_tool_plan(goal: str, explicit_requests: List[Dict[str, Any]], diagnostics: List[Dict[str, Any]], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build plan for explicit tool requests and diagnostic phrases."""
    plan: List[Dict[str, Any]] = []
    
    def add(step_id, kind, title, tool, args, requested_by_user=False, note=""):
        entry = {
            "step_id": step_id,
            "kind": kind,
            "title": title,
            "status": "planned",
            "tool_name": tool,
            "input": args,
        }
        if requested_by_user:
            entry["requested_by_user"] = True
            entry["expected"] = "ok"
        if note:
            entry["note"] = note
        plan.append(entry)
        if tool and tool not in metadata["scheduled_tools"]:
            metadata["scheduled_tools"].append(tool)
    
    # Track all tool names requested
    all_requested = set()
    
    # Process explicit tool requests
    for req in explicit_requests:
        tool_name = req["tool_name"]
        all_requested.add(tool_name)
        canonical, args, note = _resolve_tool(tool_name)
        
        if canonical:
            add(
                f"explicit_{tool_name}",
                "tool",
                f"Explicit request: {tool_name}" + (f" (resolved to {canonical})" if canonical != tool_name else ""),
                canonical,
                args,
                requested_by_user=True,
                note=note,
            )
            if note and "not available" in note.lower():
                metadata.setdefault("requested_but_unavailable", []).append({
                    "requested_tool": tool_name,
                    "resolved_to": canonical,
                    "note": note,
                })
        else:
            metadata.setdefault("requested_but_unavailable", []).append({
                "requested_tool": tool_name,
                "resolved_to": None,
                "note": note,
            })
            add(
                f"explicit_{tool_name}_unavailable",
                "summary",
                f"Tool '{tool_name}' requested but unavailable",
                None,
                {},
                requested_by_user=True,
                note=note,
            )
    
    # Process diagnostic phrases
    for diag in diagnostics:
        diag_name = diag["diagnosis"]
        for tool_name, args in diag["tools"]:
            all_requested.add(tool_name)
            canonical, resolved_args, note = _resolve_tool(tool_name)
            
            if canonical:
                add(
                    f"diag_{diag_name}_{tool_name}",
                    "tool",
                    f"Diagnostic ({diag_name}): {tool_name}" + (f" (resolved to {canonical})" if canonical != tool_name else ""),
                    canonical,
                    {**args, **resolved_args},
                    requested_by_user=False,
                    note=note,
                )
            else:
                metadata.setdefault("requested_but_unavailable", []).append({
                    "requested_tool": tool_name,
                    "diagnosis": diag_name,
                    "note": note,
                })
    
    # Add supporting evidence tools if not already scheduled
    if "repo_status_read" not in metadata["scheduled_tools"]:
        add("repo_status_support", "tool", "Supporting evidence: repository status", "repo_status_read", {})
    
    # Add grep_search for context if not already scheduled
    if "grep_search" not in metadata["scheduled_tools"]:
        add("grep_support", "tool", "Supporting evidence: code search", "grep_search", {"pattern": "agent|kernel|autonomy", "glob": "*.py"})
    
    return plan
