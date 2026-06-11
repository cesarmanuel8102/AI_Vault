# FRONT-EXTERNAL-CURATED-LEARNING-AGENTIC-SYSTEMS-01

## Objective

Create the first canonical curated source plan for Brain to learn **Agentic Systems** safely, without ingesting any content into semantic memory or FAISS, without downloading full papers or repos, and without modifying protected runtime files.

This front is **DRY-RUN ONLY / CURATION FIRST**.

## Why Agentic Systems Is First

Agentic Systems is the foundational macro-domain for Brain's autonomous operation. Before Brain can safely self-improve, evaluate, or trade, it must understand:

- How agents plan, act, and recover from failure
- How tools are governed and sandboxed
- How multi-agent systems coordinate without conflict
- How human oversight is preserved
- How state is managed, checkpointed, and rolled back

All other learning domains (evaluation, memory architecture, security, coding, trading) depend on these primitives.

## Prior Brain Learning State

Brain has:
- 1,710 lines of semantic memory (unchanged in this front)
- 1,611 FAISS IDs (unchanged in this front)
- A working chat retrieval injection patch in `session.py` (from prior fronts)
- A safe in-memory retrieval trace structure (from prior fronts)
- No prior curated external source plan for agentic systems

## Safe Source Policy

**No source is accepted because it is popular.** Every source must be:

- **Safe**: Publicly reachable, no malware, no illegal content
- **Attributable**: Clear authors, org, or maintainers
- **Technically relevant**: Concrete architecture, algorithms, or implementation
- **Cross-checked**: Verified against at least one other source type when possible
- **Mapped to Brain capability**: Directly linked to a Brain capability target
- **Legally usable at metadata level**: No full-text copying required
- **Not ingested in this front**: All sources remain `not_ingested`

## Taxonomy (14 Categories)

1. **Agent Loop Architecture** — Observe-plan-act loops and event-driven iteration
2. **Planner/Executor Separation** — Decoupling planning from execution
3. **Tool Use and Tool Governance** — Safe tool selection, invocation, schema validation
4. **Supervisor-Worker Patterns** — Orchestrator delegates with oversight
5. **Debate/Critique/Refine Patterns** — Self-critique and adversarial review
6. **Multi-Agent Communication** — Inter-agent messaging and coordination
7. **Memory in Agentic Systems** — Short-term context, long-term memory, retrieval
8. **Evaluation of Agent Behavior** — Benchmarks, drift detection, trace scoring
9. **Failure Modes** — Infinite loops, hallucinated actions, deadlock
10. **Safety/Governance Boundaries** — Permissions, sandboxes, rate limits, kill switches
11. **Human-in-the-Loop Control** — Approval gates, overrides, feedback injection
12. **Stateful Graph Workflows** — Persistent state machines, branching, rollback
13. **Coding-Agent Workflows** — Agents that write, test, review, patch code
14. **Reproducibility and Rollback** — Deterministic replay, version pinning, recovery

## Source Acceptance Criteria

- Clear attribution
- Publicly reachable URL
- Technical depth > marketing/hype
- License allows metadata reference
- Relevance to at least one taxonomy category
- Not contradicted by a more authoritative source
- No critical risk flagged by safety rubric

**Decision rule**: Accept if score >= 38 and no critical risks; hold if 28–37; reject if < 28 or any critical risk.

## Source Rejection Criteria (Automatic)

- Private or access-restricted content
- No identifiable attribution
- Illegal or copyright-violating distribution
- Core claims unverifiable
- Requires copying full copyrighted text
- Malware or suspicious repo
- Abandoned and contradicted by newer official source

## Safety Scoring Rubric

12 dimensions scored 0–5 (max 60):

| Dimension | Description |
|-----------|-------------|
| attribution_quality | Clear authors, org, or maintainers |
| primary_source_quality | Primary source vs. repackaged blog |
| technical_depth | Concrete architecture/algorithms |
| license_clarity | License stated and compatible |
| maintenance_status | Active, maintenance, or clearly archived |
| reproducibility | Reproducible steps/examples/tests |
| test_or_example_presence | Runnable examples/tests/demos |
| copyright_safety | Safe to reference at metadata level |
| relevance_to_brain | Maps to Brain capability target |
| risk_of_hype_or_marketing | Free of exaggerated claims |
| risk_of_obsolescence | Likely relevant 12+ months |
| risk_of_unverifiable_claims | Claims supported by evidence |

**Thresholds**: Accept >= 38, Hold 28–37, Reject < 28.

## Contrast Scoring Rubric

Each source contrasted against at least two sources of different types:

- paper vs official repo
- official docs vs examples/tests
- framework docs vs independent benchmark
- old repo vs release/changelog
- claim vs implementation evidence

Per-source fields: `confirms`, `contradicts`, `complements`, `unresolved_questions`, `confidence_level` (low/medium/high).

## Paper Source Candidates (10)

| Source | Authors/Org | Year | Status | Score |
|--------|-------------|------|--------|-------|
| ReAct | Yao et al. / Google | 2022 | accept | 45 |
| Reflexion | Shinn et al. / Northeastern | 2023 | accept | 44 |
| Tree of Thoughts | Yao et al. / Princeton | 2023 | accept | 45 |
| Toolformer | Schick et al. / Meta | 2023 | accept | 44 |
| Generative Agents | Park et al. / Stanford | 2023 | accept | 45 |
| CAMEL | Li et al. / KAUST | 2023 | accept | 46 |
| MetaGPT | Hong et al. / DeepWisdom | 2023 | accept | 46 |
| Voyager | Wang et al. / NVIDIA | 2023 | accept | 43 |
| SWE-agent | Yang et al. / Princeton | 2024 | accept | 47 |
| AgentBench | Liu et al. / Tsinghua | 2023 | accept | 45 |

## GitHub / Docs Candidates (11)

| Source | Org | Status | Score | Notes |
|--------|-----|--------|-------|-------|
| LangGraph | LangChain AI | active | 48 | 34.4k stars, very active |
| AutoGen | Microsoft | **maintenance** | 47 | In maintenance mode as of 2025 |
| CrewAI | crewAI Inc | active | 44 | Popular, hold for deeper audit |
| CAMEL repo | camel-ai | active | 46 | Strong community |
| MetaGPT repo | DeepWisdom | active | 46 | 68.7k stars |
| OpenAI Swarm | OpenAI | **archived** | 40 | Replaced by Agents SDK |
| SWE-agent repo | Princeton NLP | active | 47 | Superseded by mini-swe-agent |
| MCP docs | Anthropic | active | 46 | Emerging standard |
| OpenAI Agents SDK | OpenAI | active | 44 | New; monitor stability |
| LangChain docs | LangChain AI | active | 45 | Mature, some API churn |
| AgentArena | unknown | unknown | 22 | **rejected** — unverifiable |

## Cross-Source Contrast Matrix (7 pairs)

| Pair | Type | Confidence | Key Finding |
|------|------|------------|-------------|
| ReAct ↔ LangGraph | paper vs repo | high | LangGraph productionizes ReAct patterns with state persistence |
| MetaGPT ↔ MetaGPT repo | paper vs repo | high | Repo adds CI/CD and examples not in paper |
| CAMEL ↔ AutoGen | paper vs framework | medium | AutoGen has human proxy; CAMEL has role-playing data generation |
| SWE-agent ↔ SWE-agent repo | paper vs repo | high | Repo provides actual interface implementations |
| Toolformer ↔ MCP | paper vs protocol | medium | Different layers: learning method vs runtime protocol |
| Reflexion ↔ Generative Agents | paper vs paper | medium | Reflexion = task critique; GenAgents = social memory streams |
| Swarm ↔ Agents SDK | old repo vs new docs | medium | Swarm archived; SDK adds tracing/guardrails |

## Copyright Constraints

- **No full papers downloaded**
- **No full READMEs copied**
- **No repos cloned**
- **No PDFs stored in repo**
- All references are metadata-level (title, authors, URL, summary)
- arXiv papers referenced by abstract page URL only
- GitHub repos referenced by public repo URL and visible metadata only

## Dry-Run-Only Confirmation

- `ingestion_status`: `dry_run_only` for all 21 sources
- No semantic memory writes
- No FAISS reindexing
- No protected runtime modifications
- No `.env` changes
- No secrets exposed

## Memory / FAISS Immutability Proof

| Check | Before | After | Result |
|-------|--------|-------|--------|
| semantic_memory.jsonl SHA | `655d323...` | `655d323...` | **PASS** |
| semantic_memory.jsonl lines | 1710 | 1710 | **PASS** |
| FAISS index SHA | `b7b755c...` | `b7b755c...` | **PASS** |
| FAISS ids SHA | `0043623...` | `0043623...` | **PASS** |
| FAISS ids count | 1611 | 1611 | **PASS** |

## Tests Result

28 tests passed, 0 failed.

## Limitations

1. **Marker pass remains 1/3** from prior chat fronts; this front does not address chat retrieval
2. **Metadata check is sample-based** (5 of 21 sources verified via public web)
3. **AutoGen maintenance status changed** during this front; seed data updated accordingly
4. **No actual ingestion** performed; sources are candidates only
5. **Contrast matrix is manual**; future fronts may automate cross-checking

## Next Recommended Front

**FRONT-EXTERNAL-CURATED-LEARNING-EVALUATION-BENCHMARKING-01**

Purpose: Curate safe, attributable sources for evaluating and benchmarking agent behavior, including SWE-bench, AgentBench, and human-eval variants.

**Do not execute without user approval.**
