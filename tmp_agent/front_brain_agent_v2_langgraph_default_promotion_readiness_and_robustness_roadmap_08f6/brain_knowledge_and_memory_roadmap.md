# Brain Knowledge and Memory Roadmap — 08F6

## Memory categories

1. Operator profile / preferences
2. Project state
3. Front / commit ledger
4. Technical decisions
5. Lessons learned
6. Domain knowledge
7. CEI / FDOT knowledge
8. Trading / research knowledge
9. Rejected / obsolete knowledge

## Memory stores

- Structured ledger
- Semantic memory
- FAISS / vector index
- Run journal
- Decision journal
- Artifact reports

## Promotion flow

```
raw observation -> candidate memory -> validation -> human approval -> promotion -> retrieval test -> rollback/deprecation
```

## LangGraph role in memory

| Concern | LangGraph responsibility |
|---|---|
| Orchestration | Route each run through `memory_retrieval` node |
| Evidence linking | Attach evidence source IDs to retrieved context and candidate memory |
| Separation | Keep accepted memory separate from candidate memory |
| Mutation guard | Prevent silent memory mutation; all writes require explicit tool/front approval |
| Audit trail | TraceStore records retrieval attempts, source IDs, and governance decisions |

## Safeguards

- No write to memory/semantic without explicit front.
- No FAISS rebuild without explicit front.
- No auto-promotion of knowledge.
- Stale knowledge detection required.
- Evidence-linked retrieval required.
- Candidate memory must be validated before promotion.
- Human approval required for promotion.

## Brain relationship

- **Principle:** LangGraph should orchestrate Brain, not replace Brain.
- **Brain remains** the domain system owning CEI/FDOT, trading, research, and project knowledge.
- **LangGraph becomes** the controlled agentic runtime around Brain tools, memory, and governance.

## Mapping LangGraph/LangSmith capabilities to Brain needs

| Capability | How Brain should use it |
|---|---|
| Durable execution | LangGraph checkpoints and resume paths protect long-running reasoning |
| Stateful workflows | Graph state carries run context, mode, plan, and evidence source IDs |
| Human-in-the-loop | LangGraph interrupts or governance gate pause for `approval_required` mode |
| Traces | TraceStore + `capability_metadata` node provide per-run traceability |
| Rollback | CheckpointStore + env-based backend fallback provide dual rollback paths |
| Memory | `memory_retrieval` node integrates accepted memory; candidate memory kept separate |
| Tool governance | `_governance_gate_node` enforces `SUPPORTED_READ_TOOLS` and mode escalation |
| Knowledge growth | Evidence-linked retrieval feeds candidate memory; promotion requires human approval |
| Relationship with Brain/AI_Vault | LangGraph executes on behalf of Brain's goals without usurping domain ownership |
| Long-term goal execution | Graph nodes can be decomposed into future sub-agent roles after default stabilization |

## Phase result

PHASE 5 — Brain knowledge and memory roadmap: **COMPLETED**

## Recorded

`2026-06-30T18:35:00+00:00`
