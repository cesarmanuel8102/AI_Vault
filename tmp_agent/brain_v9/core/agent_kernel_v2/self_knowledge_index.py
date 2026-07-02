"""Canonical Brain self-knowledge index for Agent V2.

This module is intentionally static/read-only. It tells Agent V2 where to look
for authoritative Brain facts before it answers questions about itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BrainSelfKnowledgeDomain:
    canonical_domain: str
    description: str
    keywords: List[str]
    authoritative_files: List[str]
    authoritative_endpoints: List[str]
    required_tools: List[str]
    critical_fields: List[str]
    known_ambiguities: List[str]
    do_not_infer: List[str]
    live_vs_historical_rule: str
    recommended_next_checks: List[str]


def _domain(
    canonical_domain: str,
    description: str,
    keywords: List[str],
    authoritative_files: List[str],
    authoritative_endpoints: List[str],
    required_tools: List[str],
    critical_fields: List[str],
    known_ambiguities: List[str],
    do_not_infer: List[str],
    live_vs_historical_rule: str,
    recommended_next_checks: List[str],
) -> BrainSelfKnowledgeDomain:
    return BrainSelfKnowledgeDomain(
        canonical_domain=canonical_domain,
        description=description,
        keywords=keywords,
        authoritative_files=authoritative_files,
        authoritative_endpoints=authoritative_endpoints,
        required_tools=required_tools,
        critical_fields=critical_fields,
        known_ambiguities=known_ambiguities,
        do_not_infer=do_not_infer,
        live_vs_historical_rule=live_vs_historical_rule,
        recommended_next_checks=recommended_next_checks,
    )


DOMAINS: Dict[str, BrainSelfKnowledgeDomain] = {
    "agent_v2_runtime": _domain(
        "agent_v2_runtime",
        "Canonical Agent V2 API adapter, response contract, runtime selector, trace and run state.",
        ["agent v2", "agent", "runtime", "api adapter", "run", "trace", "chat agent", "v2"],
        [
            "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/trace.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/state.py",
        ],
        ["/v2/chat/agent", "/v2/agent/status", "/v2/agent/capabilities", "/v2/agent/runs/{run_id}/trace"],
        ["brain_self_knowledge_lookup", "repo_file_read", "route_probe", "repo_status_read"],
        ["backend_selected", "runtime_type", "run_id", "classification", "intent_route", "tool_results", "trace_url"],
        ["Dashboard proxy and 8091 canonical API may expose similar but not identical status fields."],
        ["Do not claim a tool ran unless it is present in tool_results or trace.", "Do not infer backend health from a stale evidence artifact."],
        "Use live 8091 endpoints for current runtime state; use files only for implementation contract.",
        ["Probe /v2/agent/status", "Read latest run trace", "Inspect response_normalizer contract"],
    ),
    "langgraph_parity": _domain(
        "langgraph_parity",
        "LangGraph parity backend and fallback behavior for Agent V2.",
        ["langgraph", "parity", "graph", "backend", "fallback", "timeout"],
        [
            "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py",
        ],
        ["/v2/agent/status", "/brain-dashboard/agent-v2/status"],
        ["brain_self_knowledge_lookup", "repo_file_read", "route_probe"],
        ["langgraph_default_active", "backend_fallback_used", "backend_fallback_reason", "node_path", "provider_metadata"],
        ["A timeout-degraded run can return a valid schema while not executing tools."],
        ["Do not call a timeout-degraded answer successful tool reasoning."],
        "Live status and run trace decide current behavior; code decides intended behavior.",
        ["Probe status endpoints", "Inspect last run provider_metadata", "Check trace node_path"],
    ),
    "dashboard": _domain(
        "dashboard",
        "8092 dashboard, status aggregation, frontend rendering and Agent V2 proxy.",
        ["dashboard", "ui", "frontend", "pantalla", "status", "8092", "panel"],
        [
            "tmp_agent/brain_v9/dashboard/dashboard_routes.py",
            "tmp_agent/brain_v9/dashboard/dashboard_app.py",
            "tmp_agent/brain_v9/dashboard/static/app.js",
            "tmp_agent/brain_v9/memory/memory_auditor.py",
        ],
        ["/brain-dashboard/status", "/brain-dashboard/agent-v2/status", "/brain-dashboard/chat"],
        ["brain_self_knowledge_lookup", "route_probe", "repo_file_read"],
        ["memory", "alerts", "agent_v2", "promotion_queue_count", "promotion_queue_active_review_required_count"],
        ["Raw dashboard counts may not mean active pending work unless active fields confirm it."],
        ["Do not equate raw file counts with pending candidates.", "Do not infer browser UI state without probing endpoint or browser."],
        "Use /brain-dashboard/status for live dashboard data; use app.js only to explain rendering.",
        ["Probe dashboard status", "Read dashboard_routes.py", "Read frontend field mapping"],
    ),
    "memory_semantic_faiss": _domain(
        "memory_semantic_faiss",
        "Canonical memory, semantic JSONL, FAISS index, staging and promotion audit state.",
        ["memory", "memoria", "semantic", "faiss", "journal", "staging", "promotion audit"],
        [
            "tmp_agent/brain_v9/memory/memory_auditor.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/memory_gateway.py",
            "memory/semantic/semantic_memory.jsonl",
            "memory/semantic/promotion_audit.jsonl",
        ],
        ["/brain-dashboard/status"],
        ["brain_self_knowledge_lookup", "semantic_memory_status", "memory_structure_inspect", "route_probe"],
        ["semantic_memory_lines", "faiss_ids", "faiss_ntotal", "canonical_semantic_mutated", "faiss_mutated"],
        ["Semantic memory line counts and FAISS id counts must match before claiming consistency."],
        ["Do not write semantic memory in read-only diagnostics.", "Do not assume FAISS is current without count evidence."],
        "Live safety status and filesystem counts are current; memory snippets are historical context.",
        ["Run semantic_memory_status", "Probe dashboard safety", "Compare JSONL and FAISS counts"],
    ),
    "promotion_queue": _domain(
        "promotion_queue",
        "Promotion queue files, active review state, terminal statuses and dashboard reconciliation.",
        ["promotion queue", "cola de promocion", "cola de promocion", "candidate", "candidato", "review_required", "57"],
        [
            "tmp_agent/brain_v9/core/agent_kernel_v2/evidence_tools.py",
            "tmp_agent/brain_v9/memory/memory_auditor.py",
            "tmp_agent/brain_v9/dashboard/dashboard_routes.py",
            "memory/promotion_queue/*.json",
        ],
        ["/brain-dashboard/status", "/brain/learning/status"],
        ["brain_self_knowledge_lookup", "promotion_queue_status", "route_probe"],
        ["promotion_queue_count", "active_review_required_count", "terminal_status_counts", "candidate_promote_count"],
        ["Dashboard raw file count, active review-required count, and external learning candidate count are different metrics."],
        ["Do not call raw files pending unless review_required=true.", "Do not mix /brain/learning/status proposals with semantic promotion queue files."],
        "Use promotion_queue_status for reconciled live facts; dashboard status alone is insufficient for pending interpretation.",
        ["Run promotion_queue_status", "Probe /brain-dashboard/status", "Probe /brain/learning/status if relevant"],
    ),
    "curated_knowledge": _domain(
        "curated_knowledge",
        "Read-only curated runtime lookup module, endpoints and explicit chat command.",
        ["curated", "curated knowledge", "conocimiento curado", "readonly lookup", "demo-search"],
        [
            "brain/curated_runtime_lookup.py",
            "tmp_agent/brain_v9/main.py",
            "tmp_agent/brain_v9/core/session.py",
            "tests/smoke/smoke_runtime_readonly_lookup_endpoints.py",
            "tests/smoke/smoke_runtime_readonly_lookup_chat_command.py",
        ],
        ["/brain/curated-knowledge/status", "/brain/curated-knowledge/search", "/brain/curated-knowledge/demo-search"],
        ["brain_self_knowledge_lookup", "repo_file_read", "route_probe"],
        ["verified_curated_readonly", "real_write_allowed", "faiss_write_allowed", "result_count", "source_id", "evidence_refs"],
        ["Demo index override is operator-only and not a production memory write path."],
        ["Do not treat read-only curated lookup as promoted semantic memory.", "Do not allow LLM fallback claims for curated results."],
        "Endpoint data is live read-only; fixture/demo indexes are test evidence, not canonical memory.",
        ["Probe status endpoint", "Run search endpoint if operator token available", "Check no-write flags"],
    ),
    "financial_autonomy": _domain(
        "financial_autonomy",
        "Financial autonomy package, dry-run bridge, portfolio/compliance gaps and real-money blockers.",
        [
            "financial_autonomy", "financial autonomy", "autonomia financiera",
            "autonomia financiera", "sistema financiero autonomo",
            "sistema financiero autonomo", "financiero autonomo",
            "financiero autonomo", "portfolio", "compliance", "real money",
        ],
        [
            "financial_autonomy/__init__.py",
            "financial_autonomy/bridge/financial_autonomy_bridge.py",
            "tests/smoke/test_front_financial_autonomy_compile_contract_10.py",
            "ROADMAP_STATUS.json",
        ],
        [],
        ["brain_self_knowledge_lookup", "repo_file_search", "repo_file_read", "semantic_retrieve"],
        ["broker_execution_enabled", "real_money_enabled", "dry_run", "known_blockers", "compile_status"],
        ["Some financial autonomy modules may be partial or historically broken; check compile/tests before claiming readiness."],
        ["Do not claim real-money readiness from research backtests.", "Do not enable broker execution."],
        "Use code/tests for current capability; use audit reports as historical context only.",
        ["Search safety flags", "Compile financial_autonomy package", "Read roadmap blockers"],
    ),
    "trading_qc_ibkr": _domain(
        "trading_qc_ibkr",
        "Trading research, QuantConnect paper deployment, IBKR permissions and live-paper operational status.",
        ["trading", "qc", "quantconnect", "ibkr", "paper", "broker", "hive", "strategy"],
        [
            "tmp_agent/brain_v9/trading/",
            "tmp_agent/brain_v9/financial/strategy_adapter.py",
            "tmp_agent/strategies/",
        ],
        ["/brain-dashboard/status"],
        ["brain_self_knowledge_lookup", "repo_file_search", "route_probe"],
        ["paper_trading", "broker_execution_enabled", "platform_summary", "live_status", "drawdown", "alerts"],
        ["Research artifacts, QC backtests, paper live, and real money are separate states."],
        ["Do not place real trades.", "Do not infer IBKR readiness from permissions screenshot alone.", "Do not mix research PnL with live-paper PnL."],
        "Use live platform/dashboard endpoints for current paper state; use research artifacts only for historical validation.",
        ["Probe platform summary", "Inspect latest QC live logs", "Check broker_execution_enabled=false for real money"],
    ),
    "governance_approval": _domain(
        "governance_approval",
        "RBAC, operator tokens, signed approvals, execution gate and protected paths.",
        ["governance", "approval", "signed", "operator", "token", "rbac", "execution gate", "protected"],
        [
            "tmp_agent/brain_v9/governance/execution_gate.py",
            "tmp_agent/brain_v9/governance/signed_approvals.py",
            "tmp_agent/brain_v9/api_security.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/governance.py",
            "tmp_agent/brain_v9/governance/capability_policy.py",
        ],
        ["/v2/chat/agent", "/v2/agent/status"],
        ["brain_self_knowledge_lookup", "repo_file_read", "repo_file_search"],
        ["requires_approval", "approval_required", "signed_approval_validated", "blocked_reason", "risk_level"],
        ["Dashboard proxy token and API strict operator token are related but not the same concern."],
        ["Do not print tokens/secrets.", "Do not approve P3/protected actions without signed token evidence."],
        "Use code and live 403/200 probes for current auth behavior; never expose secrets.",
        ["Read execution gate", "Run auth smoke tests", "Probe with/without operator token if safe"],
    ),
    "capabilities_tools": _domain(
        "capabilities_tools",
        "Tool registry, capability registry, planner tools, read/write boundaries and known capability gaps.",
        ["capabilities", "capacidades", "tools", "herramientas", "tool gateway", "registry"],
        [
            "tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py",
            "tmp_agent/brain_v9/core/agent_kernel_v2/governance.py",
            "tmp_agent/brain_v9/governance/capability_policy.py",
        ],
        ["/v2/agent/capabilities"],
        ["brain_self_knowledge_lookup", "capability_registry_read", "repo_file_read", "route_probe"],
        ["read_only_tools", "write_tools", "known_gaps", "approval_required", "tool_results"],
        ["Capability declaration does not prove a tool executed in a specific run."],
        ["Do not claim a capability is operational without registry plus smoke/live evidence."],
        "Use capability endpoint/registry for declared capabilities; use run traces for actual execution.",
        ["Run capability_registry_read", "Probe /v2/agent/capabilities", "Inspect tool_gateway dispatch"],
    ),
    "ci_tests": _domain(
        "ci_tests",
        "Local and GitHub validation, smoke tests, sensitive path hygiene and regression status.",
        ["ci", "tests", "pytest", "smoke", "validation", "hygiene", "github actions"],
        [
            ".github/workflows/",
            "tests/smoke/",
            "tests/unit/",
            "scripts/git_hygiene/check_no_sensitive_paths_staged.py",
        ],
        [],
        ["brain_self_knowledge_lookup", "repo_status_read", "repo_file_search", "smoke_test_readonly"],
        ["tests_passed", "py_compile", "check_no_sensitive_paths_staged", "remote_ci_status"],
        ["Local smoke pass does not imply full CI pass unless remote run is checked."],
        ["Do not claim CI green without a run id or explicit local/remote evidence."],
        "Use local test output for local validation; use GitHub checks for remote validation.",
        ["Run targeted smoke", "Run hygiene", "Check GitHub Actions when requested"],
    ),
    "known_gaps": _domain(
        "known_gaps",
        "Known open gaps from audits: live trading path, backtester, portfolio manager, compliance, E2E, microservice readiness.",
        ["gaps", "brechas", "blockers", "not ready", "production", "microservices", "auditoria", "audit"],
        [
            "ROADMAP_STATUS.json",
            "docs/MIGRATION_CONTROL_LEDGER.md",
            "C:/downloads/audit_public_brain_2026_06_18/FINAL_AUDIT_REPORT.md",
            "C:/downloads/audit_microservices_2026_06_30/FINAL_MICROSERVICES_AUDIT_REPORT.md",
        ],
        [],
        ["brain_self_knowledge_lookup", "repo_file_read", "repo_file_search"],
        ["live_trading_path", "backtester", "portfolio_manager", "compliance", "e2e_tests", "microservices_readiness"],
        ["Downloaded audit paths may not exist on every machine; repo SSOT should be preferred when missing."],
        ["Do not claim 100% production readiness while P0 blockers remain open."],
        "Use latest repo SSOT first; use downloaded audits only if present and explicitly read.",
        ["Read ROADMAP_STATUS.json", "Read ledger", "Verify audit files exist before citing"],
    ),
}


ALIASES: Dict[str, str] = {
    "runtime": "agent_v2_runtime",
    "agent": "agent_v2_runtime",
    "agent_v2": "agent_v2_runtime",
    "langgraph": "langgraph_parity",
    "ui": "dashboard",
    "memoria": "memory_semantic_faiss",
    "memory": "memory_semantic_faiss",
    "semantic": "memory_semantic_faiss",
    "faiss": "memory_semantic_faiss",
    "promotion": "promotion_queue",
    "queue": "promotion_queue",
    "curated": "curated_knowledge",
    "financial": "financial_autonomy",
    "finance": "financial_autonomy",
    "trading": "trading_qc_ibkr",
    "qc": "trading_qc_ibkr",
    "ibkr": "trading_qc_ibkr",
    "governance": "governance_approval",
    "approval": "governance_approval",
    "capabilities": "capabilities_tools",
    "tools": "capabilities_tools",
    "ci": "ci_tests",
    "tests": "ci_tests",
    "gaps": "known_gaps",
    "brechas": "known_gaps",
}


def list_self_knowledge_domains() -> List[str]:
    return sorted(DOMAINS)


def _normalize_query(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _score_domain(query: str, domain: BrainSelfKnowledgeDomain) -> int:
    score = 0
    if domain.canonical_domain.lower() in query:
        score += 8
    for keyword in domain.keywords:
        if keyword.lower() in query:
            score += 3 if " " in keyword else 2
    for field in domain.critical_fields:
        if field.lower() in query:
            score += 2
    return score


def brain_self_knowledge_lookup(query: str = "", domain: Optional[str] = None, top_k: int = 4) -> Dict[str, Any]:
    """Return authoritative Brain self-knowledge domains for a question.

    The result is a source map, not a claim that each source was already read.
    Downstream planner/finalizer must still execute the recommended read-only
    tools when current/live facts are needed.
    """
    normalized_domain = _normalize_query(domain)
    normalized_query = _normalize_query(query)
    selected: List[BrainSelfKnowledgeDomain] = []

    if normalized_domain:
        key = ALIASES.get(normalized_domain, normalized_domain)
        if key in DOMAINS:
            selected = [DOMAINS[key]]

    if not selected:
        scored = []
        for item in DOMAINS.values():
            score = _score_domain(normalized_query, item)
            if score > 0:
                scored.append((score, item.canonical_domain, item))
        scored.sort(key=lambda row: (-row[0], row[1]))
        selected = [item for _, _, item in scored[:max(1, int(top_k or 4))]]

    if not selected:
        selected = [DOMAINS["agent_v2_runtime"], DOMAINS["capabilities_tools"], DOMAINS["known_gaps"]]

    domains = [asdict(item) for item in selected]
    required_tools = sorted({tool for item in selected for tool in item.required_tools})
    authoritative_files = sorted({path for item in selected for path in item.authoritative_files})
    authoritative_endpoints = sorted({path for item in selected for path in item.authoritative_endpoints})

    return {
        "tool_name": "brain_self_knowledge_lookup",
        "ok": True,
        "mutated_state": False,
        "summary": f"Selected {len(domains)} Brain self-knowledge domain(s): " + ", ".join(d["canonical_domain"] for d in domains),
        "evidence": {
            "query": query,
            "requested_domain": domain,
            "matched_domains": domains,
            "required_tools_union": required_tools,
            "authoritative_files_union": authoritative_files,
            "authoritative_endpoints_union": authoritative_endpoints,
            "global_rules": [
                "Treat this index as a routing map, not as live state proof.",
                "Use live endpoints/tools for current state before making current-state claims.",
                "Distinguish live tool evidence from historical memory/evidence artifacts.",
                "Never infer real-money or write capability from research or paper evidence.",
            ],
        },
        "error": None,
    }
