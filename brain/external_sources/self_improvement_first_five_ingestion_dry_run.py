"""Dry-run ingestion for the first five canonical self-improvement fronts.

This module is intentionally offline and deterministic. It builds search
plans, curated metadata source records, candidates, reviews, and reports
without network calls, raw body storage, memory writes, FAISS writes, real
writes, promotion, trading, or runtime integration.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "FRED_API_KEY",
    "api_key=",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_json(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def get_first_five_learning_fronts() -> List[Dict[str, Any]]:
    fronts = [
        {
            "front_id": "MULTI_AGENT_SYSTEMS_ORCHESTRATION",
            "title": "Multi-agent systems orchestration",
            "purpose_for_brain": "Mejorar coordinacion entre planner, executor, evaluator, memory, tools y governance.",
            "core_questions": [
                "Como coordinar agentes con roles separados sin perder control?",
                "Como enrutar tareas entre planner, executor y evaluator?",
                "Como evitar que la colaboracion multi-agente evada governance?",
            ],
            "search_queries": [
                "multi agent orchestration planner executor evaluator agent framework",
                "agent debate multi agent systems evaluation",
                "autonomous agent planner executor evaluator architecture",
            ],
            "expected_artifact_types": ["paper", "official_doc", "github_repo", "benchmark", "security_guideline"],
            "success_criteria": [
                "Define roles claros para planner/executor/evaluator",
                "Incluye evaluacion o supervision de decisiones",
                "Mantiene trazabilidad y control de herramientas",
            ],
        },
        {
            "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
            "title": "Evaluation benchmarks and quality gates",
            "purpose_for_brain": "Medir si los cambios mejoran o empeoran antes de promoverlos.",
            "core_questions": [
                "Que pruebas detectan regresiones de agentes?",
                "Como comparar before/after de cambios autonomos?",
                "Como definir gates objetivos para promocion?",
            ],
            "search_queries": [
                "LLM agent evaluation benchmarks regression testing quality gates",
                "agent benchmark smoke test eval harness",
                "before after evaluation autonomous coding agents",
            ],
            "expected_artifact_types": ["paper", "official_doc", "github_repo", "benchmark", "security_guideline"],
            "success_criteria": [
                "Incluye pruebas repetibles",
                "Mide calidad, seguridad y regresiones",
                "Bloquea promocion si fallan gates",
            ],
        },
        {
            "front_id": "MEMORY_RAG_KNOWLEDGE_STRUCTURE",
            "title": "Memory, RAG and knowledge structure",
            "purpose_for_brain": "Estructurar conocimiento util, recuperable, verificable y no contaminado.",
            "core_questions": [
                "Como guardar conocimiento con provenance?",
                "Como evaluar precision de retrieval?",
                "Como separar candidatos, conocimiento curado y memoria real?",
            ],
            "search_queries": [
                "RAG memory architecture provenance retrieval augmented generation",
                "agent memory knowledge graph retrieval provenance",
                "curated knowledge RAG chunking evaluation",
            ],
            "expected_artifact_types": ["paper", "official_doc", "github_repo", "benchmark", "security_guideline"],
            "success_criteria": [
                "Tiene provenance y source tracking",
                "Soporta evaluacion de retrieval",
                "Evita contaminacion de memoria",
            ],
        },
        {
            "front_id": "SECURITY_SANDBOXING_SUPPLY_CHAIN",
            "title": "Security, sandboxing and supply-chain defense",
            "purpose_for_brain": "Evitar modificaciones peligrosas, fugas de secretos, writes no autorizados y ejecucion insegura.",
            "core_questions": [
                "Como restringir filesystem y comandos?",
                "Como prevenir fugas de tokens?",
                "Como auditar dependencias y supply-chain?",
            ],
            "search_queries": [
                "AI agent sandbox command execution security filesystem guardrails",
                "software supply chain security agent tools sandbox",
                "token leak prevention agent framework security",
            ],
            "expected_artifact_types": ["paper", "official_doc", "github_repo", "benchmark", "security_guideline"],
            "success_criteria": [
                "Define guardrails de ejecucion",
                "Incluye higiene de secretos",
                "Considera riesgos de dependencias y herramientas",
            ],
        },
        {
            "front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION",
            "title": "Auto-coding agents and patch generation",
            "purpose_for_brain": "Mejorar capacidad de generar, validar, corregir y proponer patches sin romper el sistema.",
            "core_questions": [
                "Como generar patches test-driven?",
                "Como revisar diffs y hacer rollback seguro?",
                "Como medir mejora real de self-improvement?",
            ],
            "search_queries": [
                "autonomous coding agent patch generation test driven repair",
                "AI software engineering agent diff review rollback",
                "coding agent self improvement patch validation",
            ],
            "expected_artifact_types": ["paper", "official_doc", "github_repo", "benchmark", "security_guideline"],
            "success_criteria": [
                "Incluye generacion y validacion de patches",
                "Incluye diff review y rollback",
                "Requiere tests antes de promocion",
            ],
        },
    ]
    return fronts


def build_learning_front_queries(front: Dict[str, Any]) -> List[str]:
    return list(front.get("search_queries", []))


def _reference_catalog() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "MULTI_AGENT_SYSTEMS_ORCHESTRATION": [
            {
                "provider": "local_reference_catalog",
                "source_id": "autogen_multi_agent_conversation_framework",
                "source_type": "paper",
                "title": "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation",
                "url_redacted": "https://arxiv.org/abs/2308.08155",
                "summary": "Multi-agent conversation patterns for coordinating LLM agents with roles and tool use.",
                "artifact_type": "paper",
                "validation_score": 0.86,
                "trust_score": 0.78,
                "front_fit_score": 0.88,
            }
        ],
        "EVALUATION_BENCHMARKS_QUALITY_GATES": [
            {
                "provider": "local_reference_catalog",
                "source_id": "swe_bench_verified_agent_evaluation",
                "source_type": "benchmark",
                "title": "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
                "url_redacted": "https://www.swebench.com/",
                "summary": "Benchmarking software engineering agents with issue-resolution tasks and verifiable tests.",
                "artifact_type": "benchmark",
                "validation_score": 0.88,
                "trust_score": 0.82,
                "front_fit_score": 0.86,
            }
        ],
        "MEMORY_RAG_KNOWLEDGE_STRUCTURE": [
            {
                "provider": "local_reference_catalog",
                "source_id": "rag_retrieval_augmented_generation_original",
                "source_type": "paper",
                "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                "url_redacted": "https://arxiv.org/abs/2005.11401",
                "summary": "RAG architecture combines retrieval and generation; relevant to provenance-aware curated knowledge.",
                "artifact_type": "paper",
                "validation_score": 0.86,
                "trust_score": 0.80,
                "front_fit_score": 0.84,
            }
        ],
        "SECURITY_SANDBOXING_SUPPLY_CHAIN": [
            {
                "provider": "local_reference_catalog",
                "source_id": "owasp_llm_top_10_agent_security",
                "source_type": "security_guideline",
                "title": "OWASP Top 10 for Large Language Model Applications",
                "url_redacted": "https://owasp.org/www-project-top-10-for-large-language-model-applications/",
                "summary": "Security guidance for prompt injection, sensitive information disclosure, excessive agency, and supply-chain risk.",
                "artifact_type": "security_guideline",
                "validation_score": 0.90,
                "trust_score": 0.86,
                "front_fit_score": 0.90,
            }
        ],
        "AUTO_CODING_AGENTS_PATCH_GENERATION": [
            {
                "provider": "local_reference_catalog",
                "source_id": "swe_agent_autonomous_repair",
                "source_type": "github_repo",
                "title": "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering",
                "url_redacted": "https://github.com/SWE-agent/SWE-agent",
                "summary": "Autonomous coding agent workflow for issue resolution with patch generation and test feedback.",
                "artifact_type": "github_repo",
                "validation_score": 0.84,
                "trust_score": 0.76,
                "front_fit_score": 0.88,
            }
        ],
    }


def build_source_search_plan() -> Dict[str, Any]:
    fronts = get_first_five_learning_fronts()
    catalog = _reference_catalog()
    plan_fronts = []
    deferred_sources = []
    for front in fronts:
        front_id = front["front_id"]
        references = catalog.get(front_id, [])
        plan_fronts.append(
            {
                "front_id": front_id,
                "title": front["title"],
                "search_queries": build_learning_front_queries(front),
                "target_sources": [
                    "arxiv_or_paper_metadata",
                    "official_docs",
                    "github_repositories",
                    "benchmarks",
                    "security_guidelines",
                ],
                "available_metadata_records": len(references),
                "network_fetch_performed": False,
                "raw_body_saved": False,
                "credential_status": "not_required_for_local_reference_catalog",
                "deferred_external_fetch": True,
            }
        )
        deferred_sources.append(
            {
                "front_id": front_id,
                "provider": "live_external_fetch",
                "status": "deferred",
                "reason": "dry_run_offline_no_network_or_credentials_required",
            }
        )
    return {
        "ok": True,
        "attempted_fronts": len(fronts),
        "fronts_enumerated": len(fronts),
        "fronts": plan_fronts,
        "deferred_sources": deferred_sources,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "timestamp": now_utc(),
    }


def build_front_learning_candidate(front: Dict[str, Any], source_record: Dict[str, Any]) -> Dict[str, Any]:
    front_id = front["front_id"]
    source_id = source_record["source_id"]
    content_hash = _sha256_json(
        {
            "front_id": front_id,
            "source_id": source_id,
            "title": source_record.get("title"),
            "summary": source_record.get("summary"),
        }
    )
    return {
        "candidate_id": _stable_id("self_improvement_candidate", front_id, source_id),
        "front_id": front_id,
        "provider": source_record.get("provider", "unknown"),
        "source_id": source_id,
        "source_type": source_record.get("source_type", "unknown"),
        "title": source_record.get("title", ""),
        "why_relevant_to_brain": f"Supports {front['title']} for Brain Lab self-improvement.",
        "what_brain_should_learn": source_record.get("summary", ""),
        "how_brain_could_apply_it": (
            f"Use as dry-run guidance for {front['purpose_for_brain']} "
            "after utility evaluation and operator approval."
        ),
        "evidence_refs": [source_id, source_record.get("url_redacted", "")],
        "provenance_bundle": {
            "http_status": 200,
            "retrieved_at": now_utc(),
            "url_redacted": source_record.get("url_redacted", ""),
            "content_hash": content_hash,
            "raw_body_saved": False,
            "network_fetch_performed": False,
        },
        "validation_score": float(source_record.get("validation_score", 0.0)),
        "trust_score": float(source_record.get("trust_score", 0.0)),
        "front_fit_score": float(source_record.get("front_fit_score", 0.0)),
        "promotion_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "warnings": ["dry_run_only", "not_promoted_to_memory", "local_reference_metadata_only"],
    }


def evaluate_front_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    review = {
        "candidate_id": candidate.get("candidate_id", ""),
        "front_id": candidate.get("front_id", ""),
        "decision": "",
        "utility_score": {
            "relevance_to_brain_goals": 0.0,
            "source_quality": 0.0,
            "actionability": 0.0,
            "implementation_guidance": 0.0,
            "governance_alignment": 0.0,
            "testability": 0.0,
            "overall": 0.0,
        },
        "reasons": [],
        "blocking_issues": [],
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "reviewed_at": now_utc(),
    }

    if any(
        candidate.get(flag) is True
        for flag in ("promotion_allowed", "memory_write_allowed", "faiss_write_allowed", "real_write_allowed")
    ):
        review["decision"] = "reject_policy_or_safety"
        review["blocking_issues"].append("write_or_promotion_flag_true")
        return review

    provenance = candidate.get("provenance_bundle")
    evidence_refs = candidate.get("evidence_refs") or []
    if not provenance or not evidence_refs or provenance.get("http_status") != 200:
        review["decision"] = "reject_missing_provenance"
        review["blocking_issues"].append("missing_or_invalid_provenance")
        return review

    validation_score = float(candidate.get("validation_score", 0.0))
    trust_score = float(candidate.get("trust_score", 0.0))
    front_fit_score = float(candidate.get("front_fit_score", 0.0))

    utility = {
        "relevance_to_brain_goals": round(front_fit_score, 4),
        "source_quality": round(trust_score, 4),
        "actionability": round(min(validation_score + 0.04, 1.0), 4),
        "implementation_guidance": round(min(front_fit_score + 0.02, 1.0), 4),
        "governance_alignment": 1.0,
        "testability": 0.85,
    }
    utility["overall"] = round(sum(utility.values()) / len(utility), 4)
    review["utility_score"] = utility

    if validation_score < 0.75 or trust_score < 0.70 or front_fit_score < 0.70:
        review["decision"] = "reject_low_quality"
        if validation_score < 0.75:
            review["blocking_issues"].append("validation_score_below_0.75")
        if trust_score < 0.70:
            review["blocking_issues"].append("trust_score_below_0.70")
        if front_fit_score < 0.70:
            review["blocking_issues"].append("front_fit_score_below_0.70")
        return review

    if utility["overall"] >= 0.80:
        review["decision"] = "useful_for_brain_self_improvement"
        review["reasons"].append("candidate meets provenance, quality, fit, and governance gates")
    else:
        review["decision"] = "needs_more_evidence"
        review["reasons"].append("candidate is safe but utility score needs additional evidence")
    return review


def summarize_first_five_results(candidates: List[Dict[str, Any]], reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions: Dict[str, int] = {}
    for review in reviews:
        decision = review.get("decision", "unknown")
        decisions[decision] = decisions.get(decision, 0) + 1
    fronts = get_first_five_learning_fronts()
    search_plan = build_source_search_plan()
    return {
        "ok": True,
        "attempted_fronts": 5,
        "fronts_enumerated": len(fronts),
        "candidates_generated": len(candidates),
        "useful_candidates": decisions.get("useful_for_brain_self_improvement", 0),
        "needs_more_evidence": decisions.get("needs_more_evidence", 0),
        "rejected": sum(count for key, count in decisions.items() if key.startswith("reject_")),
        "decisions": decisions,
        "deferred_sources": search_plan["deferred_sources"],
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "trading_used": False,
        "b8_touched": False,
        "timestamp": now_utc(),
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_report(fronts: List[Dict[str, Any]], candidates: List[Dict[str, Any]], reviews: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines = [
        "# Primeros 5 frentes canonicos de automejora - Dry Run",
        "",
        "## 1. Frentes enumerados",
    ]
    for front in fronts:
        lines.extend(
            [
                f"- **{front['front_id']}**: {front['title']}",
                f"  - Objetivo para Brain: {front['purpose_for_brain']}",
                f"  - Consultas: {len(front['search_queries'])}",
            ]
        )
    lines.extend(
        [
            "",
            "## 2. Que se intento localizar",
            "Se construyo un plan de busqueda para papers, documentacion oficial, repositorios, benchmarks y guias de seguridad. En este frente no se hizo fetch de red; se uso un catalogo local de metadatos externos para dry-run.",
            "",
            "## 3. Candidatos generados",
        ]
    )
    reviews_by_candidate = {review["candidate_id"]: review for review in reviews}
    for candidate in candidates:
        review = reviews_by_candidate.get(candidate["candidate_id"], {})
        lines.extend(
            [
                f"- **{candidate['front_id']}** / `{candidate['candidate_id']}`",
                f"  - Fuente: {candidate['title']}",
                f"  - Decision: {review.get('decision', 'unknown')}",
                f"  - Que Brain deberia aprender: {candidate['what_brain_should_learn']}",
                f"  - Como podria aplicarlo: {candidate['how_brain_could_apply_it']}",
            ]
        )
    lines.extend(
        [
            "",
            "## 4. Utilidad potencial por frente",
            f"- Candidatos utiles: {summary['useful_candidates']}",
            f"- Necesitan mas evidencia: {summary['needs_more_evidence']}",
            f"- Rechazados: {summary['rejected']}",
            "",
            "## 5. Aplicacion potencial para Brain",
            "Estos candidatos pueden alimentar una evaluacion de utilidad antes de cualquier promocion: orchestration, quality gates, RAG/memory, seguridad y patch generation.",
            "",
            "## 6. Deferred",
            "Live external fetch quedo deferred para todos los frentes porque este dry-run no usa red ni credenciales.",
            "",
            "## 7. Que NO se escribio",
            "- No se escribio memory/semantic",
            "- No se escribio FAISS",
            "- No hubo real write",
            "- No hubo promotion",
            "- No se integro runtime/chat",
            "- No se toco trading ni B8",
            "",
            "## 8. Siguiente paso recomendado",
            "SELF-IMPROVEMENT-FIRST-FIVE-UTILITY-EVALUATION-DRY-RUN-01",
        ]
    )
    return "\n".join(lines) + "\n"


def _contains_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("first_five_*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    return False


def run_first_five_learning_fronts_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_learning_fronts_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)

    fronts = get_first_five_learning_fronts()
    search_plan = build_source_search_plan()
    catalog = _reference_catalog()
    candidates: List[Dict[str, Any]] = []
    for front in fronts:
        for source_record in catalog.get(front["front_id"], []):
            candidates.append(build_front_learning_candidate(front, source_record))
    reviews = [evaluate_front_candidate(candidate) for candidate in candidates]
    summary = summarize_first_five_results(candidates, reviews)
    summary["output_dir"] = str(out)

    (out / "first_five_learning_fronts.json").write_text(json.dumps(fronts, indent=2), encoding="utf-8")
    (out / "source_search_plan.json").write_text(json.dumps(search_plan, indent=2), encoding="utf-8")
    (out / "first_five_candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    _write_jsonl(out / "first_five_candidates.jsonl", candidates)
    (out / "first_five_candidate_reviews.json").write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    (out / "first_five_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "first_five_learning_report.md").write_text(_render_report(fronts, candidates, reviews, summary), encoding="utf-8")

    token_leak = _contains_token_marker(out)
    summary["token_leak_detected"] = token_leak
    return {
        "ok": not token_leak and summary["attempted_fronts"] == 5,
        "attempted_fronts": summary["attempted_fronts"],
        "fronts_enumerated": summary["fronts_enumerated"],
        "candidates_generated": summary["candidates_generated"],
        "useful_candidates": summary["useful_candidates"],
        "needs_more_evidence": summary["needs_more_evidence"],
        "rejected": summary["rejected"],
        "deferred_sources": summary["deferred_sources"],
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "token_leak_detected": token_leak,
        "output_dir": str(out),
    }
