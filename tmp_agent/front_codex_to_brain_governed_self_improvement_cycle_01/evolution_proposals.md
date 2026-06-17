# Evolution Proposals

- proposals_created: `9`

## EP-001 — Open WebUI provider config using 8091
- priority: `P1`
- risk_level: `medium`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-CHAT-UI-BRAIN-PROVIDER-CONFIG-8091-01`
- objective: Configure UI provider to use verified adapter endpoint on 8091.
- current_gap: UI not yet configured for 8091 provider URL.

## EP-002 — Runtime switchover 8091 to 8090
- priority: `P0`
- risk_level: `high`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-BRAIN-V9-RUNTIME-SWITCHOVER-8091-TO-8090-01`
- objective: Replace old 8090 runtime with verified 8091 runtime using safe owner classification or manual approval.
- current_gap: 8090 still serves old runtime without /v1 adapter.

## EP-003 — Import/TestClient side-effect hardening
- priority: `P1`
- risk_level: `medium`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-BRAIN-V9-IMPORT-SIDE-EFFECTS-HARDENING-01`
- objective: Prevent main.py/TestClient imports from mutating tmp_agent/knowledge/external/github JSON.
- current_gap: Prior adapter front detected import side effects.

## EP-004 — Brain autonomous observer reports
- priority: `P2`
- risk_level: `low`
- requires_human_approval: `False`
- recommended_front_name: `FRONT-BRAIN-AUTONOMOUS-OBSERVER-REPORTS-01`
- objective: Define mandatory report format after each autonomous cycle.
- current_gap: No standard observer report after autonomous cycles yet.

## EP-005 — CEI/FDOT evaluation pack
- priority: `P2`
- risk_level: `low`
- requires_human_approval: `False`
- recommended_front_name: `FRONT-CEI-FDOT-EVALUATION-PACK-01`
- objective: Create CEI/FDOT benchmark prompts, expected evidence behavior, and uncertainty rubric.
- current_gap: Current CEI/FDOT answers often timed out and are not benchmarked.

## EP-006 — Financial research safety pack
- priority: `P2`
- risk_level: `medium`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-FINANCIAL-RESEARCH-SAFETY-PACK-01`
- objective: Define no-live-trading boundaries, risk-limit language, and evaluation tests.
- current_gap: Financial research needs enforceable tests before integration with trading work.

## EP-007 — Memory/FAISS retrieval quality pack
- priority: `P2`
- risk_level: `medium`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-MEMORY-FAISS-RETRIEVAL-QUALITY-PACK-01`
- objective: Evaluate retrieval quality without mutation using canonical FAISS counts and evidence traces.
- current_gap: Memory/FAISS respected but quality is not continuously scored.

## EP-008 — Codex-to-Brain recurring evaluation harness
- priority: `P1`
- risk_level: `medium`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-CODEX-TO-BRAIN-EVALUATION-HARNESS-V2-01`
- objective: Turn this one-off cycle into a repeatable harness with timeout classification.
- current_gap: Current cycle is ad hoc and exposed timeout fallback rate.

## EP-009 — LLM timeout quality stabilization
- priority: `P0`
- risk_level: `high`
- requires_human_approval: `True`
- recommended_front_name: `FRONT-BRAIN-V9-LLM-TIMEOUT-QUALITY-STABILIZATION-01`
- objective: Diagnose and reduce LLM timeout fallback on 8091 route.
- current_gap: 20/24 prompts returned timeout fallback despite 200 status.

