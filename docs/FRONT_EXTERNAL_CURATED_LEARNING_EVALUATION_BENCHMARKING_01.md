# FRONT-EXTERNAL-CURATED-LEARNING-EVALUATION-BENCHMARKING-01

## Objective

Create a canonical curated source plan for Brain to learn **Evaluation & Benchmarking** safely, without ingesting any content into semantic memory or FAISS, without downloading full papers or repos, and without modifying protected runtime files.

This front is **DRY-RUN ONLY / CURATION FIRST**.

## Why Evaluation & Benchmarking Is Second

After understanding agentic systems (macro-order 1), Brain must learn how to **measure** those systems before trusting them to act autonomously. Evaluation is the gate between learning and deployment. Without robust benchmarking, Brain cannot:

- Detect regressions after patches or ingestion
- Validate that retrieved context improves responses
- Measure groundedness and hallucination rates
- Decide whether to promote, reject, or rollback changes
- Prepare for domain-specific financial strategy evaluation

## Prior Brain Learning State

- Agentic Systems curated plan complete (21 sources, 14 taxonomy categories)
- 1,710 lines of semantic memory (unchanged in this front)
- 1,611 FAISS IDs (unchanged in this front)
- Chat retrieval injection patch present but marker pass remains 1/3
- No prior curated external source plan for evaluation/benchmarking

## Safe Source Policy

**No evaluation source is accepted because it is popular.** Every source must be:

- **Safe**: Publicly reachable, no malware, no illegal content
- **Attributable**: Clear authors, org, or maintainers
- **Technically relevant**: Concrete methodology, metrics, or reproducible protocols
- **Cross-checked**: Verified against at least one other source type when possible
- **Mapped to Brain capability**: Directly linked to a Brain evaluation target
- **Legally usable at metadata level**: No full-text copying required
- **Not ingested in this front**: All sources remain `not_ingested`

## Taxonomy (15 Categories)

1. **Agent Task Success Evaluation** — Did the agent complete the task correctly?
2. **Tool-Use Correctness** — Right tool, valid parameters, correct interpretation
3. **Retrieval Quality Evaluation** — Relevance, ranking, noise control
4. **Groundedness / Faithfulness** — Output factually supported by sources
5. **Hallucination Detection** — Detecting invented facts, citations, actions
6. **Regression Testing** — Detecting improvements that break other things
7. **Benchmark Design** — Fair, reproducible, representative test suites
8. **Human Preference Evaluation** — Collecting and aggregating human judgments
9. **Automated Judge Evaluation** — LLM/rule-based scoring at scale
10. **Trace-Based Evaluation** — Scoring agent trajectories and reasoning steps
11. **Safety Evaluation** — Harmful outputs, policy violations, jailbreak resistance
12. **Cost / Latency / Reliability Metrics** — Time, cost, failure rate, retries
13. **Before-After Capability Measurement** — Quantified delta after changes
14. **Promote / Reject / Rollback Decision Logic** — Rules and thresholds for go/no-go
15. **Domain-Specific Financial Evaluation Readiness** — Preparing for trading strategy validation

## Source Acceptance Criteria

- Clear attribution
- Publicly reachable URL
- Technical depth > marketing/hype
- License allows metadata reference
- Relevance to at least one taxonomy category
- Not contradicted by a more authoritative source
- No critical risk flagged by safety rubric

**Decision rule**: Accept if score >= 48 and no critical risks; hold if 35-47; reject if < 35 or any critical risk.

## Source Rejection Criteria (Automatic)

- Private or access-restricted content
- No identifiable attribution
- Illegal or copyright-violating distribution
- Unverifiable benchmark claims
- Benchmark data leakage risk not disclosed
- Requires copying full copyrighted text
- Malware or suspicious repo
- Abandoned and contradicted by newer official source

## Safety Scoring Rubric

15 dimensions scored 0-5 (max 75):

| Dimension | Description |
|-----------|-------------|
| attribution_quality | Clear authors, org, or maintainers |
| primary_source_quality | Primary source vs. repackaged blog |
| technical_depth | Concrete methodology, metrics, protocols |
| evaluation_method_clarity | Steps, metrics, baselines clearly defined |
| reproducibility | Reproducible steps/examples/tests |
| benchmark_validity | Representative, not cherry-picked, no data leakage |
| license_clarity | License stated and compatible |
| maintenance_status | Active, maintenance, or clearly archived |
| test_or_example_presence | Runnable examples/tests/demos |
| copyright_safety | Safe to reference at metadata level |
| relevance_to_brain | Maps to Brain capability target |
| risk_of_hype_or_marketing | Free of exaggerated claims |
| risk_of_obsolescence | Likely relevant 12+ months |
| risk_of_metric_gaming | Known gaming/overfitting risks |
| risk_of_unverifiable_claims | Claims supported by evidence |

**Thresholds**: Accept >= 48, Hold 35-47, Reject < 35.

## Contrast Scoring Rubric

Each source contrasted against at least two sources of different types:

- paper vs benchmark repo
- official eval framework docs vs examples/tests
- leaderboard claim vs independent benchmark methodology
- automated judge method vs human eval method
- retrieval eval metric vs groundedness metric
- safety eval source vs task success benchmark

Per-source fields: `confirms`, `contradicts`, `complements`, `unresolved_questions`, `confidence_level` (low/medium/high).

## Brain Evaluation Capability Map (12 Capabilities)

| Capability | Relevant Taxonomy | Example Sources |
|------------|-------------------|-----------------|
| Evaluate FAISS retrieval quality | retrieval quality, regression | RAGAS, AgentBench |
| Evaluate chat memory usage | retrieval quality, trace-based | SWE-agent, Reflexion |
| Evaluate groundedness | groundedness, hallucination | TruthfulQA, SelfCheckGPT |
| Evaluate CoT leakage | safety, trace-based | AgentBench, DeepEval |
| Evaluate tool-use correctness | tool-use, task success | SWE-bench, AgentBench |
| Evaluate latency stability | cost/latency, regression | LangSmith, chat diagnostics |
| Evaluate patch quality | before/after, regression | SWE-bench, SWE-agent |
| Evaluate regression risk | regression, before/after | AgentBench, BIG-bench |
| Evaluate governance compliance | safety, promote/reject/rollback | DeepEval, promptfoo |
| Evaluate financial claims | financial readiness, benchmark | HELM, AgentBench |
| Decide promote/reject/rollback | promote/reject/rollback, before/after | RAGAS, AgentBench |
| Produce scorecards | before/after, benchmark design | OpenAI Evals, lm-eval-harness |

## Paper Source Candidates (10)

| Source | Authors/Org | Year | Status | Score |
|--------|-------------|------|--------|-------|
| AgentBench | Liu et al. / Tsinghua | 2023 | accept | 52 |
| SWE-bench | Jimenez et al. / Princeton | 2023 | accept | 55 |
| SWE-agent | Yang et al. / Princeton | 2024 | accept | 56 |
| WebArena | Zhou et al. / CMU | 2023 | accept | 53 |
| HELM | Liang et al. / Stanford | 2022 | accept | 55 |
| BIG-bench | Srivastava et al. / Google | 2022 | accept | 54 |
| TruthfulQA | Lin et al. / Anthropic | 2021 | accept | 53 |
| SelfCheckGPT | Manakul et al. / Cambridge | 2023 | accept | 50 |
| G-Eval | Liu et al. / Salesforce | 2023 | accept | 49 |
| MT-Bench | Zheng et al. / LMSYS | 2023 | accept | 52 |

## GitHub / Docs Candidates (14)

| Source | Org | Status | Score | Notes |
|--------|-----|--------|-------|-------|
| OpenAI Evals | OpenAI | active | 52 | YAML-based eval registry |
| lm-eval-harness | EleutherAI | active | 53 | Hundreds of benchmarks |
| HELM repo | Stanford CRFM | active | 54 | Multi-metric scorecards |
| RAGAS | Exploding Gradients | active | 52 | RAG pipeline metrics |
| DeepEval | Confident AI | active | 50 | Python-native, CI/CD ready |
| TruLens | TruEra | active | 50 | Instrumentation + eval |
| LangSmith | LangChain AI | active | 48 | Hosted tracing + eval |
| promptfoo | promptfoo | active | 50 | Red-team + regression |
| AgentBench repo | THUDM | active | 52 | Benchmark environments |
| WebArena repo | CMU | active | 51 | Self-hosted web tasks |
| SWE-bench repo | Princeton NLP | active | 55 | Execution-based coding eval |
| Chatbot Arena | LMSYS | active | 48 | Live leaderboard |
| MiniWoB++ | Stanford NLP | maintenance | 44 | **Hold** — older, less representative |
| Unknown Eval Blog | unknown | unknown | 18 | **Reject** — no attribution |

## Cross-Source Contrast Matrix (8 pairs)

| Pair | Type | Confidence | Key Finding |
|------|------|------------|-------------|
| AgentBench ↔ AgentBench repo | paper vs repo | high | Repo adds harnesses and Docker |
| SWE-bench ↔ SWE-bench repo | paper vs repo | high | Execution verification prevents hallucinated fixes |
| HELM ↔ lm-eval-harness | paper vs framework | high | HELM = transparency; harness = breadth |
| RAGAS ↔ TruthfulQA | framework vs benchmark | medium | RAGAS = automated metrics; TruthfulQA = adversarial QA |
| G-Eval ↔ MT-Bench | judge paper vs benchmark | medium | G-Eval = zero-shot judge; MT-Bench = multi-turn convo |
| SelfCheckGPT ↔ DeepEval | paper vs framework | medium | SelfCheckGPT = lightweight; DeepEval = full framework |
| SWE-agent ↔ SWE-bench | paper vs benchmark | high | SWE-bench defines benchmark; SWE-agent defines interface |
| WebArena ↔ MiniWoB++ | modern vs older | medium | WebArena realistic; MiniWoB++ maintenance mode |

## Metric Gaming Risks

| Source | Risk | Notes |
|--------|------|-------|
| MT-Bench / Chatbot Arena | medium | Bias toward verbose responses; position bias in pairwise |
| BIG-bench | medium | Some tasks may be memorized by large models |
| WebArena | medium | Execution-based reduces but doesn't eliminate gaming |
| MiniWoB++ | medium | Synthetic tasks less representative of modern web |
| Unknown Eval Blog | high | No methodology; likely SEO content |

## Copyright Constraints

- **No full papers downloaded**
- **No full READMEs copied**
- **No repos cloned**
- **No PDFs stored in repo**
- All references are metadata-level (title, authors, URL, summary)
- arXiv papers referenced by abstract page URL only
- GitHub repos referenced by public repo URL and visible metadata only

## Dry-Run-Only Confirmation

- `ingestion_status`: `dry_run_only` for all 24 sources
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

31 tests passed, 0 failed.

## Limitations

1. **Marker pass remains 1/3** from prior chat fronts; this front does not address chat retrieval
2. **Metadata check is sample-based** (no full web verification run)
3. **No actual ingestion** performed; sources are candidates only
4. **Contrast matrix is manual**; future fronts may automate cross-checking
5. **MiniWoB++ held** due to age and maintenance status
6. **Unknown Eval Blog rejected** due to lack of attribution

## Next Recommended Front

**FRONT-EXTERNAL-CURATED-LEARNING-MEMORY-RAG-KNOWLEDGE-ARCHITECTURE-01**

Purpose: Curate safe, attributable sources for Memory, RAG, and Knowledge Architecture — the third macro-domain in Brain's external learning plan.

**Do not execute without user approval.**
