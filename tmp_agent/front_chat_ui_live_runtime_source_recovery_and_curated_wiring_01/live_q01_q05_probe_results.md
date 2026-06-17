# Live Q01-Q05 Probe Results
Endpoint: POST http://127.0.0.1:8090/chat
Date: 2026-06-11

## Q01
- model_used: curated_helper
- success: True
- route: ?
- response:
```
Decision: explain
Domains used: agentic_systems, evaluation_benchmarking, memory_rag_knowledge_architecture, security_governance_sandboxing, autonomous_coding_patch_generation, financial_motor_trading_intelligence
Sources or source types used: all_curated_modules
Policy constraints applied: read_only, no_memory_claim, no_faiss_claim
Risk flags: 
Final answer:
Dominios curados completados (6 dominios):
- Agentic Systems: 21 sources, 19 accepted, 1 hold, 1 rejected, 14 taxonomy, 0 capabilities — Planning, tool use, multi-agent orchestration under governance controls
- Evaluation & Benchmarking: 24 sources, 22 accepted, 1 hold, 1 rejected, 15 taxonomy, 12 capabilities — Metrics, benchmarks, and statistical rigor for validation
- Memory / RAG / Knowledge Architecture: 28 sources, 25 accepted, 2 hold, 1 rejected, 20 taxonomy, 16 capabilities — Retrieval, embeddings, and FAISS indexing infrastructure
- Security / Governance / Sandboxing: 23 sources, 22 accepted, 0 hold, 1 rejected, 22 taxonomy, 18 capabilities — Guardrails, protected paths, sandboxing, and approval gates
- Autonomous Coding & Patch Generation: 24 sources, 23 accepted, 0 hold, 1 rejected, 25 taxonomy, 20 capabilities — Diff generation, git hygiene, and code review capabilities
- Financial Motor / Trading Intelligence: 32 sources, 31 accepted, 0 hold, 1 rejected, 32 taxonomy, 24 capabilities — Risk-first framework, position sizing, drawdown control; no trading execution

Totales: 152 sources, 142 accepted, 4 hold, 6 rejected.
Confidence: high
```

## Q02
- model_used: curated_helper
- success: True
- route: ?
- response:
```
Decision: explain
Domains used: all_curated_domains
Sources or source types used: rejected_sources
Policy constraints applied: source_exclusion_policy, source_rejection_criteria
Risk flags: no_attribution, guaranteed_returns, signal_selling
Final answer:
Fuentes rechazadas:
- AgentArena — Open Evaluation Framework for LLM Agents (agentic_systems): Metadata too sparse. Unverifiable maintenance and authorship. Reject until better attribution found.
- 10 Ways to Evaluate Your LLM -- Unattributed Blog Post (evaluation_benchmarking): No attribution. No evidence. SEO content. Reject.
- Top 10 Vector Databases You Must Use -- Unattributed Blog (memory_rag_knowledge_architecture): No attribution. No evidence. SEO content. Reject.
- 10 AI Security Tips -- Unattributed Blog Post (security_governance_sandboxing): No attribution. No evidence. SEO content. Reject.
- 10 AI Coding Tools You Must Use -- Unattributed Blog Post (autonomous_coding_patch_generation): No attribution. No evidence. SEO content. Reject.
- 10 Guaranteed Trading Strategies — Unattributed Blog (financial_motor_trading_intelligence): No attribution. Guaranteed returns. Signal selling. Auto-reject.

Razones comunes: falta de atribución, promesas de retornos garantizados, venta de señales, contenido SEO sin metodología verificable.
Confidence: high
```

## Q03
- model_used: curated_helper
- success: True
- route: ?
- response:
```
Decision: explain
Domains used: security_governance_sandboxing, memory_rag_knowledge_architecture, evaluation_benchmarking, agentic_systems, autonomous_coding_patch_generation, financial_motor_trading_intelligence
Sources or source types used: domain_authorization_matrix
Policy constraints applied: financial_domain_locked, coding_domain_locked, explicit_approval_required
Risk flags: financial_risk=high, execution_risk=high, advice_risk=high
Final answer:
Autorizados para canary: security_governance_sandboxing, memory_rag_knowledge_architecture, evaluation_benchmarking, agentic_systems (con cautela).
Bloqueados: autonomous_coding_patch_generation, financial_motor_trading_intelligence.
Requiere aprobación explícita de usuario para cualquier mutación futura.
Confidence: high
```

## Q04
- model_used: curated_helper
- success: True
- route: ?
- response:
```
Decision: explain
Domains used: security_governance_sandboxing, controlled_ingestion_authorization
Sources or source types used: canary_policy
Policy constraints applied: first_canary_scope, one_domain_only
Risk flags: 
Final answer:
Primer canary: security_governance_sandboxing. Rango: 3-5 records.
Justificación: enseña restricciones, no acciones; menor riesgo de ejecución/trading; no coding self-modification; accept-only sources; metadata summary only.
Confidence: high
```

## Q05
- model_used: curated_helper
- success: True
- route: ?
- response:
```
Decision: deny
Domains used: controlled_ingestion_authorization
Sources or source types used: batch_limits
Policy constraints applied: mass_ingestion_denied, canary_max_5, explicit_approval_required
Risk flags: mass_ingestion_risk, contamination_risk
Final answer:
Denegado. No se aprueba ingesta masiva.
Canary máximo: 5 records.
Requisitos: backup obligatorio, rollback plan, retrieval eval pre/post, aprobación humana explícita. No se escribe memory. No se modifica FAISS.
Confidence: high
```

