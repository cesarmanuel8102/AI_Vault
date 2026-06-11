"""Chat-safe curated learning access helper.

Read-only helper that exposes curated learning inventory to Chat/UI/Agent.
No memory/FAISS mutation.
No broker/API.
No trading.
No executable code returned.
"""

import json
from typing import Any
from datetime import datetime, timezone


###############################################################################
# Front identity
###############################################################################

def front_id() -> str:
    return "FRONT-EXTERNAL-CURATED-LEARNING-CHAT-UI-USAGE-REPAIR-01"


###############################################################################
# Module registry
###############################################################################

_CURATED_MODULES = [
    ("brain.external_curated_learning_agentic_systems", "agentic_systems", "Agentic Systems", "Planning, tool use, multi-agent orchestration under governance controls"),
    ("brain.external_curated_learning_evaluation_benchmarking", "evaluation_benchmarking", "Evaluation & Benchmarking", "Metrics, benchmarks, and statistical rigor for validation"),
    ("brain.external_curated_learning_memory_rag_knowledge_architecture", "memory_rag_knowledge_architecture", "Memory / RAG / Knowledge Architecture", "Retrieval, embeddings, and FAISS indexing infrastructure"),
    ("brain.external_curated_learning_security_governance_sandboxing", "security_governance_sandboxing", "Security / Governance / Sandboxing", "Guardrails, protected paths, sandboxing, and approval gates"),
    ("brain.external_curated_learning_autonomous_coding_patch_generation", "autonomous_coding_patch_generation", "Autonomous Coding & Patch Generation", "Diff generation, git hygiene, and code review capabilities"),
    ("brain.external_curated_learning_financial_motor_trading_intelligence", "financial_motor_trading_intelligence", "Financial Motor / Trading Intelligence", "Risk-first framework, position sizing, drawdown control; no trading execution"),
]


###############################################################################
# Inventory
###############################################################################

def get_canonical_curated_learning_inventory() -> dict[str, Any]:
    """Compute canonical inventory directly from curated modules."""
    domains = []
    totals = {"source_count": 0, "accepted_count": 0, "hold_count": 0, "rejected_count": 0}
    mismatch_notes = []

    for mod_name, dom_id, display_name, practical_capability in _CURATED_MODULES:
        try:
            mod = __import__(mod_name, fromlist=["build_curated_learning_plan", "seed_candidate_sources"])
            plan = mod.build_curated_learning_plan()
            summary = plan["summary"]
            src_count = summary["source_count"]
            acc_count = summary["accepted_count"]
            hold_count = summary["hold_count"]
            rej_count = summary["rejected_count"]
            tax_count = summary["taxonomy_count"]

            cap_count = summary.get("capability_map_count")
            if cap_count is None:
                try:
                    cap_func_name = None
                    for attr in dir(mod):
                        if "capability_map" in attr.lower() and callable(getattr(mod, attr)):
                            cap_func_name = attr
                            break
                    if cap_func_name:
                        cap_count = len(getattr(mod, cap_func_name)())
                    else:
                        cap_count = 0
                except Exception:
                    cap_count = 0

            totals["source_count"] += src_count
            totals["accepted_count"] += acc_count
            totals["hold_count"] += hold_count
            totals["rejected_count"] += rej_count

            domains.append({
                "domain": dom_id,
                "display_name": display_name,
                "source_count": src_count,
                "accepted_count": acc_count,
                "hold_count": hold_count,
                "rejected_count": rej_count,
                "taxonomy_count": tax_count,
                "capability_map_count": cap_count,
                "ingestion_status": summary.get("ingestion_status", "dry_run_only"),
                "memory_mutated": summary.get("memory_mutated", True),
                "faiss_mutated": summary.get("faiss_mutated", True),
                "practical_capability_added": practical_capability,
            })
        except Exception as e:
            domains.append({
                "domain": dom_id,
                "display_name": display_name,
                "error": str(e),
            })
            mismatch_notes.append(f"{dom_id}: {e}")

    # Check against previously reported values
    previous_reports = {
        "agentic_systems": {"source_count": 21, "accepted_count": 19},
        "evaluation_benchmarking": {"source_count": 24, "accepted_count": 22},
        "memory_rag_knowledge_architecture": {"source_count": 28, "accepted_count": 25},
        "security_governance_sandboxing": {"source_count": 25, "accepted_count": 24},
        "autonomous_coding_patch_generation": {"source_count": 24, "accepted_count": 23},
        "financial_motor_trading_intelligence": {"source_count": 28, "accepted_count": 27},
    }

    for d in domains:
        if "error" in d:
            continue
        dom = d["domain"]
        prev = previous_reports.get(dom, {})
        if prev:
            if d["source_count"] != prev.get("source_count") or d["accepted_count"] != prev.get("accepted_count"):
                mismatch_notes.append(
                    f"{dom}: computed src={d['source_count']} acc={d['accepted_count']} "
                    f"vs prev src={prev.get('source_count')} acc={prev.get('accepted_count')}"
                )

    return {
        "domains": domains,
        "totals": totals,
        "count_source": "computed_from_curated_modules",
        "count_mismatch_detected": len(mismatch_notes) > 0,
        "mismatch_notes": mismatch_notes,
    }


###############################################################################
# Rejected sources summary
###############################################################################

def get_rejected_sources_summary() -> list[dict]:
    """Collect all rejected sources across curated modules."""
    rejected = []
    for mod_name, dom_id, display_name, _ in _CURATED_MODULES:
        if dom_id == "controlled_ingestion_authorization":
            continue
        try:
            mod = __import__(mod_name, fromlist=["seed_candidate_sources"])
            sources = mod.seed_candidate_sources()
            for s in sources:
                if s.get("acceptance_status") == "reject":
                    rejected.append({
                        "source_id": s.get("source_id"),
                        "title": s.get("title"),
                        "domain": dom_id,
                        "reason": s.get("notes", "rejected"),
                        "risk_flags": [],
                    })
        except Exception:
            pass
    return rejected


###############################################################################
# Canary ingestion policy
###############################################################################

def get_canary_ingestion_policy() -> dict[str, Any]:
    """Return canary policy from controlled ingestion authorization."""
    try:
        mod = __import__("brain.external_curated_learning_controlled_ingestion_authorization", fromlist=["build_controlled_ingestion_authorization_plan"])
        plan = mod.build_controlled_ingestion_authorization_plan()
        summary = plan["summary"]
        first_canary = plan.get("first_canary_scope", {})
        return {
            "first_canary_domain": first_canary.get("recommended_first_domain", "security_governance_sandboxing"),
            "first_canary_record_min": first_canary.get("allowed_record_count_min", 3),
            "first_canary_record_max": first_canary.get("allowed_record_count_max", 5),
            "allowed_source_status": first_canary.get("allowed_source_status", ["accept"]),
            "forbidden_source_status": first_canary.get("forbidden_source_status", ["hold", "reject", "candidate"]),
            "financial_domain_locked": summary.get("financial_domain_locked", True),
            "autonomous_coding_domain_locked": summary.get("autonomous_coding_domain_locked", True),
            "mass_ingestion_allowed": False,
            "actual_memory_mutation_authorized": summary.get("actual_memory_mutation_authorized", False),
            "actual_faiss_mutation_authorized": summary.get("actual_faiss_mutation_authorized", False),
            "requires_future_user_approval_for_mutation": summary.get("requires_future_user_approval_for_mutation", True),
        }
    except Exception as e:
        return {"error": str(e), "first_canary_domain": "security_governance_sandboxing"}


###############################################################################
# Chat probe answers
###############################################################################

def answer_chat_probe(question: str | None = None, probe_id: str | None = None) -> dict[str, Any]:
    """Answer a curated learning probe question in chat-safe format."""
    inventory = get_canonical_curated_learning_inventory()
    policy = get_canary_ingestion_policy()
    rejected = get_rejected_sources_summary()
    q = (question or "").lower()

    if probe_id == "Q01" or ("dominios" in q and "completados" in q):
        return _answer_q01(inventory)
    elif probe_id == "Q02" or "rechazadas" in q:
        return _answer_q02(rejected)
    elif probe_id == "Q03" or ("autorizados" in q and "bloqueados" in q):
        return _answer_q03(inventory, policy)
    elif probe_id == "Q04" or ("primer dominio" in q and "canary" in q):
        return _answer_q04(policy)
    elif probe_id == "Q05" or "ingesta masiva" in q:
        return _answer_q05(policy)
    elif probe_id == "Q06" or ("4 records" in q and "security" in q):
        return _answer_q06(policy)
    elif probe_id == "Q07" or ("fuentes financieras" in q and "primero" in q):
        return _answer_q07(policy)
    elif probe_id == "Q08" or ("autonomous coding" in q and "primero" in q):
        return _answer_q08(policy)
    elif probe_id == "Q09" or ("hold" in q and "canary" in q):
        return _answer_q09(policy)
    elif probe_id == "Q10" or ("sin url" in q or "sin autores" in q):
        return _answer_q10(policy)
    else:
        return {
            "decision": "explain",
            "domains_used": ["controlled_ingestion_authorization"],
            "sources_or_source_types_used": [],
            "policy_constraints_applied": ["unknown_probe"],
            "risk_flags": [],
            "final_answer": "No tengo una respuesta canónica para esta pregunta en el helper de curated learning. Por favor, especifica el probe_id (Q01-Q05) o reformula la pregunta.",
            "confidence": "low",
        }


def _answer_q01(inventory: dict) -> dict:
    lines = []
    for d in inventory["domains"]:
        if "error" in d:
            continue
        lines.append(
            f"- {d['display_name']}: {d['source_count']} sources, {d['accepted_count']} accepted, "
            f"{d['hold_count']} hold, {d['rejected_count']} rejected, {d['taxonomy_count']} taxonomy, "
            f"{d['capability_map_count']} capabilities — {d['practical_capability_added']}"
        )
    totals = inventory["totals"]
    final = (
        f"Dominios curados completados ({len([d for d in inventory['domains'] if 'error' not in d])} dominios):\n"
        + "\n".join(lines)
        + f"\n\nTotales: {totals['source_count']} sources, {totals['accepted_count']} accepted, "
        f"{totals['hold_count']} hold, {totals['rejected_count']} rejected."
    )
    return {
        "decision": "explain",
        "domains_used": [d["domain"] for d in inventory["domains"] if "error" not in d],
        "sources_or_source_types_used": ["all_curated_modules"],
        "policy_constraints_applied": ["read_only", "no_memory_claim", "no_faiss_claim"],
        "risk_flags": [],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q02(rejected: list) -> dict:
    lines = []
    for r in rejected:
        lines.append(f"- {r['title']} ({r['domain']}): {r['reason']}")
    final = (
        "Fuentes rechazadas:\n"
        + "\n".join(lines)
        + "\n\nRazones comunes: falta de atribución, promesas de retornos garantizados, "
        "venta de señales, contenido SEO sin metodología verificable."
    )
    return {
        "decision": "explain",
        "domains_used": ["all_curated_domains"],
        "sources_or_source_types_used": ["rejected_sources"],
        "policy_constraints_applied": ["source_exclusion_policy", "source_rejection_criteria"],
        "risk_flags": ["no_attribution", "guaranteed_returns", "signal_selling"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q03(inventory: dict, policy: dict) -> dict:
    auth = ["security_governance_sandboxing", "memory_rag_knowledge_architecture", "evaluation_benchmarking", "agentic_systems"]
    locked = ["autonomous_coding_patch_generation", "financial_motor_trading_intelligence"]
    final = (
        "Autorizados para canary: security_governance_sandboxing, memory_rag_knowledge_architecture, "
        "evaluation_benchmarking, agentic_systems (con cautela).\n"
        "Bloqueados: autonomous_coding_patch_generation, financial_motor_trading_intelligence.\n"
        "Requiere aprobación explícita de usuario para cualquier mutación futura."
    )
    return {
        "decision": "explain",
        "domains_used": auth + locked,
        "sources_or_source_types_used": ["domain_authorization_matrix"],
        "policy_constraints_applied": ["financial_domain_locked", "coding_domain_locked", "explicit_approval_required"],
        "risk_flags": ["financial_risk=high", "execution_risk=high", "advice_risk=high"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q04(policy: dict) -> dict:
    final = (
        f"Primer canary: {policy['first_canary_domain']}. "
        f"Rango: {policy['first_canary_record_min']}-{policy['first_canary_record_max']} records.\n"
        "Justificación: enseña restricciones, no acciones; menor riesgo de ejecución/trading; "
        "no coding self-modification; accept-only sources; metadata summary only."
    )
    return {
        "decision": "explain",
        "domains_used": ["security_governance_sandboxing", "controlled_ingestion_authorization"],
        "sources_or_source_types_used": ["canary_policy"],
        "policy_constraints_applied": ["first_canary_scope", "one_domain_only"],
        "risk_flags": [],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q05(policy: dict) -> dict:
    final = (
        "Denegado. No se aprueba ingesta masiva.\n"
        f"Canary máximo: {policy['first_canary_record_max']} records.\n"
        "Requisitos: backup obligatorio, rollback plan, retrieval eval pre/post, "
        "aprobación humana explícita. No se escribe memory. No se modifica FAISS."
    )
    return {
        "decision": "deny",
        "domains_used": ["controlled_ingestion_authorization"],
        "sources_or_source_types_used": ["batch_limits"],
        "policy_constraints_applied": ["mass_ingestion_denied", "canary_max_5", "explicit_approval_required"],
        "risk_flags": ["mass_ingestion_risk", "contamination_risk"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q06(policy: dict) -> dict:
    final = (
        "Deferido. Requiero paquete de aprobación completo antes de mutación:\n"
        "- domain: security_governance_sandboxing\n"
        "- batch_id: identificador único\n"
        "- source_ids: lista exacta de 4 fuentes accepted\n"
        "- record_count: 4\n"
        "- faiss_eligible_count: cuántos van a FAISS\n"
        "- backup_path y rollback_path confirmados\n"
        "- expected memory line count y FAISS ids count after\n"
        "Sin paquete completo: no mutation."
    )
    return {
        "decision": "defer",
        "domains_used": ["controlled_ingestion_authorization"],
        "sources_or_source_types_used": ["human_approval_requirements"],
        "policy_constraints_applied": ["approval_package_mandatory", "no_mutation_without_approval"],
        "risk_flags": ["incomplete_approval_package"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q07(policy: dict) -> dict:
    final = (
        "Denegado. financial_motor_trading_intelligence está locked_until_later.\n"
        "Riesgo de contaminación de advice/signals. No broker/API. No trading execution. "
        "No strategy execution. Financiero debe esperar hasta que governance, memory y evaluation estén probados."
    )
    return {
        "decision": "deny",
        "domains_used": ["controlled_ingestion_authorization", "financial_motor_trading_intelligence"],
        "sources_or_source_types_used": ["domain_authorization_matrix"],
        "policy_constraints_applied": ["financial_domain_locked", "no_trading", "no_advice"],
        "risk_flags": ["financial_risk=high", "advice_risk=high", "signal_risk=medium"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q08(policy: dict) -> dict:
    final = (
        "Denegado. autonomous_coding_patch_generation está locked_until_later.\n"
        "Riesgo de influencia en self-modification. Archivos protegidos deben permanecer protegidos. "
        "Coding ingestion requiere que governance ingestion esté probado primero."
    )
    return {
        "decision": "deny",
        "domains_used": ["controlled_ingestion_authorization", "autonomous_coding_patch_generation"],
        "sources_or_source_types_used": ["domain_authorization_matrix"],
        "policy_constraints_applied": ["coding_domain_locked", "protected_paths", "no_self_modification"],
        "risk_flags": ["self_modification_risk", "execution_risk=high"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q09(policy: dict) -> dict:
    final = (
        "Denegado. Canary: accept-only. Excluidos: hold, reject, candidate.\n"
        "Fuente hold tiene metadata incompleta o riesgo pendiente. No entra al canary hasta resolver a accept."
    )
    return {
        "decision": "deny",
        "domains_used": ["controlled_ingestion_authorization"],
        "sources_or_source_types_used": ["source_to_memory_record_policy"],
        "policy_constraints_applied": ["accept_only", "hold_excluded"],
        "risk_flags": ["hold_source_risk", "incomplete_metadata"],
        "final_answer": final,
        "confidence": "high",
    }


def _answer_q10(policy: dict) -> dict:
    final = (
        "Denegado. Exclusiones automáticas: unknown attribution, no URL, no license or legal status.\n"
        "Sin provenance no hay verificabilidad. No se aceptan fuentes sin metadatos mínimos."
    )
    return {
        "decision": "deny",
        "domains_used": ["controlled_ingestion_authorization"],
        "sources_or_source_types_used": ["source_exclusion_policy"],
        "policy_constraints_applied": ["attribution_required", "url_required", "license_required"],
        "risk_flags": ["no_attribution", "no_provenance"],
        "final_answer": final,
        "confidence": "high",
    }


###############################################################################
# Chat-safe context builder
###############################################################################

def build_chat_safe_context(max_chars: int = 6000) -> str:
    """Build a read-only context string safe to inject into chat prompts."""
    inventory = get_canonical_curated_learning_inventory()
    policy = get_canary_ingestion_policy()

    lines = ["=== BRAIN CURATED LEARNING INVENTORY ===", ""]
    lines.append(f"Total domains: {len([d for d in inventory['domains'] if 'error' not in d])}")
    lines.append(f"Total sources: {inventory['totals']['source_count']}")
    lines.append(f"Total accepted: {inventory['totals']['accepted_count']}")
    lines.append(f"Total hold: {inventory['totals']['hold_count']}")
    lines.append(f"Total rejected: {inventory['totals']['rejected_count']}")
    lines.append("")

    for d in inventory["domains"]:
        if "error" in d:
            lines.append(f"[ERROR] {d['display_name']}: {d['error']}")
            continue
        lines.append(
            f"- {d['display_name']}: {d['source_count']} src, {d['accepted_count']} acc, "
            f"{d['hold_count']} hold, {d['rejected_count']} rej, {d['taxonomy_count']} tax, "
            f"{d['capability_map_count']} cap"
        )

    lines.append("")
    lines.append("=== CANARY POLICY ===")
    lines.append(f"First canary domain: {policy.get('first_canary_domain', 'N/A')}")
    lines.append(f"First canary range: {policy.get('first_canary_record_min', 'N/A')}-{policy.get('first_canary_record_max', 'N/A')} records")
    lines.append(f"Mass ingestion allowed: {policy.get('mass_ingestion_allowed', False)}")
    lines.append(f"Financial locked: {policy.get('financial_domain_locked', True)}")
    lines.append(f"Coding locked: {policy.get('autonomous_coding_domain_locked', True)}")
    lines.append(f"Memory mutation authorized: {policy.get('actual_memory_mutation_authorized', False)}")
    lines.append(f"FAISS mutation authorized: {policy.get('actual_faiss_mutation_authorized', False)}")
    lines.append("")
    lines.append("=== RULES ===")
    lines.append("- Read-only helper. No memory/FAISS mutation.")
    lines.append("- No broker/API. No trading. No strategy execution.")
    lines.append("- No chain-of-thought. No executable code returned.")
    lines.append("- Canary first: 3-5 records, security_governance_sandboxing only.")
    lines.append("- Human approval required for any mutation.")
    lines.append("- Rejected sources excluded. Hold sources excluded from canary.")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text
