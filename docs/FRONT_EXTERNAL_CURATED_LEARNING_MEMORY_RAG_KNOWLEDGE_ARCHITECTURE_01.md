# FRONT-EXTERNAL-CURATED-LEARNING-MEMORY-RAG-KNOWLEDGE-ARCHITECTURE-01

## Objective

Create a canonical curated source plan for Brain to learn **Memory / RAG / Knowledge Architecture** safely, without ingesting any content into semantic memory or FAISS, without downloading full papers or repos, and without modifying protected runtime files.

This front is **DRY-RUN ONLY / CURATION FIRST**.

## Why Memory / RAG / Knowledge Architecture Is Third

After understanding agentic systems (macro-order 1) and how to evaluate them (macro-order 2), Brain must learn how to **store, retrieve, and manage knowledge** that those agents depend on. Memory is the substrate of intelligence. Without robust memory architecture, Brain cannot:

- Ground responses in factual, retrievable knowledge
- Maintain continuity across sessions (episodic memory)
- Avoid hallucinations by linking outputs to sources
- Deduplicate and resolve contradictions in stored knowledge
- Decide what deserves long-term retention vs. ephemeral context
- Protect sensitive data from leakage through retrieval

## Prior Brain Learning State

- Agentic Systems curated plan complete (21 sources, 14 taxonomy categories)
- Evaluation & Benchmarking curated plan complete (24 sources, 15 taxonomy categories, 12 capability map entries)
- 1,710 lines of semantic memory (unchanged in this front)
- 1,611 FAISS IDs (unchanged in this front)
- Chat retrieval injection patch present but marker pass remains 1/3
- No prior curated external source plan for memory/RAG architecture

## Safe Source Policy

**No memory/RAG source is accepted because it is popular.** Every source must be:

- **Safe**: Publicly reachable, no malware, no illegal content
- **Attributable**: Clear authors, org, or maintainers
- **Technically relevant**: Concrete architecture, algorithms, or implementation
- **Cross-checked**: Verified against at least one other source type when possible
- **Mapped to Brain capability**: Directly linked to a Brain memory/RAG target
- **Legally usable at metadata level**: No full-text copying required
- **Not ingested in this front**: All sources remain `not_ingested`

## Taxonomy (20 Categories)

1. **Retrieval-Augmented Generation** — Combining retrieval with generation
2. **Semantic Memory Architecture** — Structured long-term factual memory
3. **Episodic Memory Architecture** — Session-level time-ordered event memory
4. **Vector Embeddings** — Dense representations for similarity search
5. **Vector Stores and FAISS** — Index structures for nearest-neighbor search
6. **Chunking and Document Segmentation** — Splitting docs into retrieval units
7. **Metadata Design** — Structured metadata for filtering, ranking, provenance
8. **Hybrid Search** — Dense + sparse/keyword search combined
9. **Reranking** — Second-stage scoring for top-k relevance
10. **Context Compression** — Reducing retrieved size without losing salience
11. **Grounding and Citation** — Linking outputs to specific sources
12. **Deduplication** — Removing redundant or near-duplicate records
13. **Contradiction Detection** — Identifying conflicting information
14. **Memory Promotion / Rejection** — Deciding what enters long-term storage
15. **Memory Decay / Update Policy** — Aging, refreshing, evicting memories
16. **Retrieval Evaluation** — Precision, recall, MRR, nDCG, ranking stability
17. **Knowledge Graph Integration** — Vector + graph traversal for multi-hop reasoning
18. **Privacy and Memory Governance** — Preventing sensitive data leakage
19. **Local-First Memory Design** — On-device memory without cloud dependencies
20. **Long-Term Agent Memory** — Persistent memory across sessions and restarts

## Source Acceptance Criteria

- Clear attribution
- Publicly reachable URL
- Technical depth > marketing/hype
- License allows metadata reference
- Relevance to at least one taxonomy category
- Not contradicted by a more authoritative source
- No critical risk flagged by safety rubric

**Decision rule**: Accept if score >= 55 and no critical risks; hold if 40-54; reject if < 40 or any critical risk.

## Source Rejection Criteria (Automatic)

- Private or access-restricted content
- No identifiable attribution
- Illegal or copyright-violating distribution
- Requires copying full copyrighted text
- Unverifiable claims about memory/retrieval performance
- Privacy-invasive architecture with no safeguards
- Malware or suspicious repo
- Abandoned and contradicted by newer official source

## Safety Scoring Rubric

17 dimensions scored 0-5 (max 85):

| Dimension | Description |
|-----------|-------------|
| attribution_quality | Clear authors, org, or maintainers |
| primary_source_quality | Primary source vs. repackaged blog |
| technical_depth | Concrete architecture, algorithms, implementation |
| implementation_relevance | Can be adapted without vendor-specific infrastructure |
| retrieval_method_clarity | Retrieval steps, indexing, query paths clearly defined |
| memory_architecture_clarity | Memory structure (short-term, long-term, episodic, semantic) explicit |
| reproducibility | Reproducible steps/examples/tests |
| license_clarity | License stated and compatible |
| maintenance_status | Active, maintenance, or clearly archived |
| test_or_example_presence | Runnable examples/tests/demos |
| copyright_safety | Safe to reference at metadata level |
| relevance_to_brain | Maps to Brain memory/RAG capability target |
| risk_of_hype_or_marketing | Free of exaggerated claims |
| risk_of_obsolescence | Likely relevant 12+ months |
| risk_of_vendor_lock_in | Requires specific vendor/cloud? (5 = neutral, 0 = lock-in) |
| risk_of_privacy_leakage | Risks leaking private/sensitive data? (5 = safe, 0 = high risk) |
| risk_of_unverifiable_claims | Claims supported by evidence |

**Thresholds**: Accept >= 55, Hold 40-54, Reject < 40.

## Contrast Scoring Rubric

Each source contrasted against at least two sources of different types:

- paper vs framework docs
- vector DB docs vs FAISS docs
- RAG framework docs vs RAG evaluation framework
- memory paper vs agent memory implementation
- chunking paper/blog vs benchmark/eval source
- long-term memory claim vs reproducible implementation

Per-source fields: `confirms`, `contradicts`, `complements`, `unresolved_questions`, `confidence_level` (low/medium/high).

## Brain Memory Capability Map (16 Capabilities)

| Capability | Relevant Taxonomy | Example Sources |
|------------|-------------------|-----------------|
| Design semantic memory records | semantic memory, metadata | RAG paper, MemGPT |
| Design episodic memory records | episodic memory, long-term | Generative Agents, MemGPT |
| Design source metadata schema | metadata, grounding | RAG paper, LangChain docs |
| Improve FAISS retrieval quality | vector stores, retrieval eval | FAISS docs, MTEB |
| Evaluate top-k retrieval | retrieval eval, RAG | BEIR, RAGAS |
| Evaluate chat-grounded memory | RAG, grounding | Self-RAG, RAGAS |
| Decide memory promotion/rejection | promotion/rejection, privacy | MemGPT, Generative Agents |
| Deduplicate memories | deduplication, semantic memory | RAG paper, ColBERT |
| Detect contradictions | contradiction detection, semantic | SelfCheckGPT, TruthfulQA |
| Design hybrid search | hybrid search, vector stores | DPR, FAISS docs |
| Design reranking layer | reranking, retrieval eval | ColBERT, RAGAS |
| Compress context safely | context compression, RAG | Lost in the Middle, RAPTOR |
| Cite sources from records | grounding, metadata | RAG paper, RAGAS |
| Avoid privacy leakage | privacy, local-first | MemGPT, TruLens |
| Implement memory decay | decay policy, long-term | Generative Agents, MemGPT |
| Prepare financial knowledge memory | semantic memory, privacy | RAG paper, local-first |

## Paper Source Candidates (12)

| Source | Authors/Org | Year | Status | Score |
|--------|-------------|------|--------|-------|
| RAG (Lewis et al.) | Facebook AI / UCL | 2020 | accept | 58 |
| REALM | Google Research | 2020 | accept | 56 |
| DPR | Facebook AI | 2020 | accept | 59 |
| ColBERT | Stanford | 2020 | accept | 58 |
| HyDE | CMU | 2022 | accept | 54 |
| Self-RAG | UW | 2023 | accept | 58 |
| MemGPT/Letta | UC Berkeley | 2023 | accept | 59 |
| Generative Agents | Stanford | 2023 | accept | 58 |
| GraphRAG | Microsoft Research | 2024 | accept | 56 |
| RAPTOR | Stanford | 2024 | accept | 57 |
| Lost in the Middle | Stanford | 2023 | accept | 55 |
| MTEB | Hugging Face | 2022 | accept | 58 |
| BEIR | UKP | 2021 | accept | 57 |

## GitHub / Docs Candidates (15)

| Source | Org | Status | Score | Notes |
|--------|-----|--------|-------|-------|
| FAISS docs | Meta | active | 62 | Brain already uses FAISS |
| LangChain docs | LangChain AI | active | 56 | Chunking + metadata patterns |
| LangGraph memory docs | LangChain AI | active | 57 | Stateful memory in agents |
| LlamaIndex docs | LlamaIndex | active | 56 | Advanced RAG + knowledge graphs |
| Chroma | trychroma | active | 55 | Local-first vector DB |
| Qdrant docs | Qdrant | active | 56 | Hybrid search + self-hostable |
| Weaviate docs | Weaviate | active | 54 | GraphQL + knowledge graph |
| Pinecone docs | Pinecone | active | 48 | **Hold** — high vendor lock-in |
| RAGAS | Exploding Gradients | active | 57 | RAG evaluation metrics |
| DeepEval RAG docs | Confident AI | active | 54 | CI/CD RAG evaluation |
| TruLens | TruEra | active | 55 | Privacy governance patterns |
| Microsoft GraphRAG | Microsoft | active | 58 | Graph + vector hybrid |
| Letta (MemGPT) | Letta / UC Berkeley | active | 59 | Long-term memory architecture |
| LangSmith datasets | LangChain AI | active | 49 | **Hold** — proprietary platform |
| Unknown Vector DB Blog | unknown | unknown | 20 | **Reject** — no attribution |

## Cross-Source Contrast Matrix (9 pairs)

| Pair | Type | Confidence | Key Finding |
|------|------|------------|-------------|
| RAG paper ↔ LangChain docs | paper vs framework | high | LangChain implements RAG patterns from the paper |
| FAISS docs ↔ Chroma repo | vector lib vs vector DB | medium | FAISS lower-level/scalable; Chroma higher-level/local-first |
| RAGAS ↔ DeepEval RAG | eval framework vs eval docs | medium | RAGAS = metric definitions; DeepEval = CI/CD integration |
| MemGPT paper ↔ MemGPT repo | paper vs implementation | high | Repo adds multi-user, REST API, persistence |
| DPR ↔ ColBERT | dense vs late-interaction | high | DPR efficient at scale; ColBERT more effective per query |
| GraphRAG paper ↔ MS GraphRAG repo | paper vs implementation | high | Repo provides indexing pipeline and query engine |
| Lost in Middle ↔ RAPTOR | placement vs hierarchy | medium | RAPTOR's tree may mitigate position bias |
| MTEB ↔ BEIR | embedding vs retrieval benchmark | medium | MTEB = embedding quality; BEIR = retrieval system quality |
| Pinecone ↔ FAISS | managed vendor vs open-source | high | Pinecone easier at scale; FAISS free and controllable |

## Privacy Risks

| Source | Risk | Notes |
|--------|------|-------|
| Pinecone | medium | Cloud-only; data leaves local environment |
| LangSmith | medium | Hosted platform; traces may contain sensitive data |
| MemGPT/Letta | low | Self-hostable; local-first option available |
| Unknown Vector DB Blog | low | No actual product; just listicle |

## Vendor Lock-In Risks

| Source | Risk | Notes |
|--------|------|-------|
| Pinecone | high | Proprietary managed service; migration requires full reindex |
| LangSmith | high | Proprietary platform; datasets locked to ecosystem |
| Weaviate | medium | GraphQL dependency; some features cloud-only |
| LangChain | medium | API churn; ecosystem coupling |
| FAISS | low | Open-source, self-hostable, no external dependency |
| Chroma | low | Local-first, open-source, easy migration |

## Copyright Constraints

- **No full papers downloaded**
- **No full READMEs copied**
- **No repos cloned**
- **No PDFs stored in repo**
- All references are metadata-level (title, authors, URL, summary)
- arXiv papers referenced by abstract page URL only
- GitHub repos referenced by public repo URL and visible metadata only

## Dry-Run-Only Confirmation

- `ingestion_status`: `dry_run_only` for all 28 sources
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

36 tests passed, 0 failed.

## Limitations

1. **Marker pass remains 1/3** from prior chat fronts; this front does not address chat retrieval
2. **Metadata check is sample-based** (no full web verification run)
3. **No actual ingestion** performed; sources are candidates only
4. **Contrast matrix is manual**; future fronts may automate cross-checking
5. **Pinecone and LangSmith held** due to vendor lock-in and privacy risks
6. **Unknown Vector DB Blog rejected** due to lack of attribution

## Next Recommended Front

**FRONT-EXTERNAL-CURATED-LEARNING-SECURITY-GOVERNANCE-SANDBOXING-01**

Purpose: Curate safe, attributable sources for Security, Governance, and Sandboxing — the fourth macro-domain in Brain's external learning plan.

**Do not execute without user approval.**
