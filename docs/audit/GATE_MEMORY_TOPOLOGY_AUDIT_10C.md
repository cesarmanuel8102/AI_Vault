# FRONT-BRAIN-GATE-MEMORY-TOPOLOGY-AUDIT-10C

Status: COMPLETE_LOCAL_AUDIT
Branch: codex/own-capital-sustainable-return
Base HEAD audited: d11af25
Scope: read-only topology audit of Brain gate, memory, rooms, curated ingestion, semantic promotion, FAISS, and SCVL placement.

## Executive Verdict

Brain currently has several memory and gate layers, but they are not yet a single coherent promotion pipeline. The topology is usable for audited read-only operation, but it is not safe to wire SCVL directly into memory promotion until session memory isolation and semantic promotion boundaries are tightened.

Key verdicts:

- `session_memory_state.py` has a confirmed global artifact race: `build_session_memory(session_id)` reads session-specific inputs but writes to one global `tmp_agent/state/session_memory.json` artifact.
- `validate_semantic_coherence()` exists, but the audit did not confirm production wiring as a mandatory final-answer or semantic-promotion gate.
- Curated ingestion/promotion remains intentionally dry-run oriented and should stay that way until semantic promotion gates are explicit.
- `SemanticMemoryFAISS.promote_record()` is the correct canonical promotion boundary, and `promotion_candidate_promoter.py` now uses it.
- Legacy/direct semantic memory writers still exist and must be governed before claiming a single safe memory write path.
- Rooms are active cross-session/autonomy state, but hardcoded legacy paths and freshness/dedupe risks remain.

Recommended next front: `FRONT-BRAIN-SESSION-MEMORY-ISOLATION-FIX-10D` before SCVL wiring.

## Runtime Inventory Snapshot

Observed runtime artifacts under `C:/AI_VAULT_CANONICAL`:

| Artifact | Exists | Size | Count / Notes |
|---|---:|---:|---|
| `memory/semantic/semantic_memory.jsonl` | yes | 876,667 bytes | 1,794 JSONL records |
| `memory/semantic/semantic_memory_faiss_ids.json` | yes | 50,777 bytes | 1,794 ids |
| `memory/semantic/semantic_memory_faiss.index` | yes | 5,511,213 bytes | FAISS index present |
| `tmp_agent/state/session_memory.json` | yes | 2,044 bytes | global artifact, current `session_id=openai_compat` |
| `memory/rooms` | yes | directory | 2 children: `cesar_main`, `test_room` |
| `tmp_agent/state/rooms` | yes | directory | 4 children sampled |

Semantic JSONL top kinds:

| Kind | Count |
|---|---:|
| `session_fragment` | 1,358 |
| `task_result` | 293 |
| `canonical_candidate` | 63 |
| `error` | 49 |
| `codex_training_lesson` | 12 |
| `candidate` | 8 |
| `canonical_promoted` | 5 |
| `project_context` | 2 |

Semantic JSONL top sources:

| Source | Count |
|---|---:|
| `session_memory_import` | 1,358 |
| `agent_loop` | 342 |
| `promotion_queue` | 59 |
| `09d_batch_promotion` | 8 |
| `FRONT-BRAIN-CODEX-PURE-BRAIN-AUTONOMOUS-TRAINING-AND-PENDING-DRAIN-01` | 6 |
| `HOTFIX-CURRENT-RUN-KEEP-KNOWLEDGE-ADD-MISSING-CORE-DOMAINS` | 6 |
| `canonical_memory_promotion` | 5 |
| `semantic_staging` | 4 |

## Layer Map

### 1. Intra-session memory assembly

Files:

- `tmp_agent/brain_v9/core/session_memory_state.py`

Runtime data:

- Reads: `_cfg.MEMORY_PATH / session_id / short_term.json`
- Reads: `_cfg.MEMORY_PATH / session_id / long_term.json`
- Reads: `_cfg.STATE_PATH / utility_u_latest.json`
- Reads: `_cfg.STATE_PATH / meta_governance_status_latest.json`
- Reads: `_cfg.STATE_PATH / security/security_posture_latest.json`
- Writes: `tmp_agent/state/session_memory.json`

Observed API:

- `build_session_memory(session_id)`
- `get_session_memory_latest(session_id)`

Gate status:

- No dedicated coherence or promotion gate confirmed inside this layer.
- It is a context assembly layer, not a safe promotion boundary.

Risk:

- Global artifact race. `get_session_memory_latest(session_id)` checks whether the global artifact matches the requested session and rebuilds otherwise. Concurrent sessions can overwrite each other.

Recommended action:

- 10D should isolate the artifact per session or introduce a lock/namespace strategy before SCVL or autonomous memory decisions depend on this artifact.

### 2. Rooms and cross-session state

Files / references observed:

- `tmp_agent/agent_state.py`
- `tmp_agent/brain_v9/config.py`
- `tmp_agent/brain_v9/agent/tools.py`
- `tmp_agent/brain_v9/brain/*`
- Legacy references in `00_identity/*` and backups

Runtime data:

- `tmp_agent/state/rooms/*`
- `memory/rooms/*`

Observed concerns:

- Some current/legacy paths still reference hardcoded `C:/AI_VAULT` or `C:\AI_VAULT` roots.
- Rooms are a cross-session operational state mechanism, not a semantic promotion boundary.
- Freshness, dedupe, and canonical ownership are not fully centralized.

Recommended action:

- Keep rooms out of SCVL semantic promotion until ownership, path normalization, and freshness rules are documented and enforced.

### 3. Legacy JSONL semantic memory

File:

- `tmp_agent/brain_v9/core/semantic_memory.py`

Observed writer APIs:

- `SemanticMemory.ingest_text()` writes JSONL records.
- `SemanticMemory.ingest_many()` calls ingestion paths.
- `SemanticMemory.ingest_session_memory()` ingests session context.
- `SemanticMemory.compact()` can rewrite records, with dry-run support.
- `SemanticMemory._write_status()` writes status metadata.

Read APIs:

- `SemanticMemory.search()`
- `SemanticMemory.status()`

Gate status:

- This legacy layer exposes direct write APIs and is not itself a final semantic promotion gate.

Risk:

- Direct ingestion can bypass a future SCVL promotion gate if callers are not forced through a canonical boundary.

Recommended action:

- 11B should either deprecate or hard-gate direct writers for protected production routes.

### 4. FAISS semantic memory

File:

- `tmp_agent/brain_v9/core/semantic_memory_faiss.py`

Runtime data:

- `memory/semantic/semantic_memory.jsonl`
- `memory/semantic/semantic_memory_faiss.index`
- `memory/semantic/semantic_memory_faiss_ids.json`

Observed writer APIs:

- `SemanticMemoryFAISS.ingest_text()` writes JSONL and adds to FAISS.
- `SemanticMemoryFAISS.promote_record()` writes an externally built canonical record and adds it to FAISS.
- `SemanticMemoryFAISS.compact()` rewrites JSONL and can rebuild index.
- `SemanticMemoryFAISS.rebuild_index()` / `_save_index()` rewrite FAISS/index metadata.

Canonical promotion boundary:

- `SemanticMemoryFAISS.promote_record()` is the correct boundary for canonical promotions.
- `tmp_agent/brain_v9/memory/promotion_candidate_promoter.py` uses `mem.promote_record(semantic_record, rebuild=True)`.
- The promoter explicitly avoids `ingest_text()` because it would generate a new record id instead of preserving the candidate id.

Risk:

- `ingest_text()` remains a public writer and can still bypass canonical promotion semantics.
- Maintenance APIs can mutate FAISS/JSONL and need explicit governance when exposed operationally.

Recommended action:

- 11B should wire SCVL and governance at `promote_record()` and prohibit production promotion through `ingest_text()` unless explicitly approved.

### 5. Memory gateway / RBAC

Audit result:

- This audit did not confirm a single central MemoryGateway class governing every semantic write.
- Execution governance exists elsewhere, but semantic writes remain distributed across legacy and FAISS classes.

Risk:

- Brain can have strong route governance while still allowing multiple memory write surfaces internally.

Recommended action:

- Define an explicit memory ownership contract: read APIs, write APIs, promotion APIs, maintenance APIs, and which routes may call each.

### 6. Curated external ingestion

Files / modules observed:

- `brain/external_sources/*`
- `brain/external_curated_learning_*`
- `brain/curated_memory_*`

Status:

- Curated ingestion and promotion contracts are intentionally dry-run oriented.
- Several modules and reports explicitly preserve no-real-write and dry-run semantics.

Risk:

- Safe as long as dry-run invariants remain enforced.
- Unsafe if connected to semantic promotion without SCVL and promotion boundary enforcement.

Recommended action:

- Keep curated ingestion read-only/dry-run until 10D and 11B are complete.

### 7. Curated promotion and governance

Files / modules observed:

- `brain/curated_memory_promotion.py`
- `brain/curated_memory_governance.py`
- `brain/curated_memory_governance_audit.py`
- `brain/curated_memory_observability.py`
- Related rollback/report modules

Status:

- These modules model promotion governance, observability, and rollback concepts.
- They do not replace the real semantic JSONL/FAISS promotion boundary.

Recommended action:

- Treat curated governance as pre-promotion evidence, not as permission to write canonical memory.

### 8. Semantic Coherence Validation Layer (SCVL)

File:

- `tmp_agent/brain_v9/core/session_chat_metrics.py`

Observed API:

- `validate_semantic_coherence(user_message, selected_route, response_content=None, tools_used=None)`

Related docs/tests:

- `docs/SEMANTIC_COHERENCE_VALIDATION_LAYER.md`
- `docs/CONTRADICTION_LEARNING_LAYER.md`
- `tests/unit/test_semantic_coherence_validation.py`
- `tests/unit/test_b7_routing_heuristics_characterization.py`

Audit result:

- SCVL implementation exists.
- This audit did not confirm mandatory production wiring in the final answer path or semantic promotion path.

Recommended 11A insertion point:

- Final answer surface: after route/tool execution and response normalization, before the answer is returned to chat UI.
- Candidate files to inspect for 11A: `tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py`, `tmp_agent/brain_v9/core/response_normalizer.py`, `tmp_agent/brain_v9/core/session_agent_route.py`, and `tmp_agent/brain_v9/core/session.py`.

Recommended 11B insertion point:

- Semantic promotion boundary: before `SemanticMemoryFAISS.promote_record()` is called, and/or inside `promote_record()` itself for defense in depth.
- Candidate files to inspect for 11B: `tmp_agent/brain_v9/memory/promotion_candidate_promoter.py`, `tmp_agent/brain_v9/core/semantic_memory_faiss.py`.

Do not wire SCVL before 10D because session context can be stale or from another session.

### 9. Finalizer and final response layer

Files:

- `tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py`
- `tmp_agent/brain_v9/core/response_normalizer.py`
- `tmp_agent/brain_v9/core/session_agent_route.py`

Observed behavior:

- The finalizer has an identity preamble and explicit no-chain-of-thought markers.
- It can call provider models through Ollama-compatible endpoints and has structured fallback logic.

Risk:

- Final response quality and self-knowledge can improve without being a memory promotion gate.
- If SCVL is only applied here, it protects visible answer correctness but not semantic memory mutation.

Recommended action:

- 11A should gate final answers here.
- 11B must separately gate semantic promotion.

### 10. Agent route and Tool01 layer

Files:

- `tmp_agent/brain_v9/core/session_agent_route.py`
- `tmp_agent/brain_v9/core/session.py`
- Tool gateway modules created by recent B7 strangler phases

Status:

- Recent 10B split extracted agent route concerns and CI was green at `d11af25`.
- This is routing/execution plumbing, not a canonical memory promotion boundary.

Risk:

- Tool output can feed final answer or memory decisions. SCVL should inspect tool-grounded evidence before final answer and before promotion.

## Findings

### GMTA-10C-001: Session memory global artifact race is confirmed

Evidence:

- `SESSION_MEMORY_ARTIFACT = _cfg.STATE_PATH / "session_memory.json"`
- `build_session_memory(session_id)` reads session-specific memory but writes one global artifact.
- Runtime artifact currently exists as `tmp_agent/state/session_memory.json` with `session_id=openai_compat`.

Impact:

- Multi-session or concurrent chat state can contaminate SCVL inputs.
- A validator can reason over stale or wrong session context.

Recommendation:

- 10D must fix session memory isolation before SCVL activation.

### GMTA-10C-002: SCVL exists but mandatory production wiring was not confirmed

Evidence:

- `validate_semantic_coherence()` exists in `session_chat_metrics.py`.
- Tests and docs exist.
- Grep did not establish mandatory final-answer or semantic-promotion enforcement.

Impact:

- SCVL is a capability, not yet an enforced system invariant.

Recommendation:

- 11A: final answer gate.
- 11B: semantic promotion gate.

### GMTA-10C-003: Curated promotion remains dry-run oriented

Evidence:

- Curated modules and reports repeatedly encode dry-run and no-real-write semantics.

Impact:

- Safe for evidence generation and lookup, not equivalent to real semantic memory promotion.

Recommendation:

- Preserve dry-run until semantic promotion boundary is gated.

### GMTA-10C-004: FAISS/JSONL integrity boundary is real but not exclusive

Evidence:

- `SemanticMemoryFAISS.promote_record()` exists and is used by `promotion_candidate_promoter.py`.
- FAISS IDs count matches semantic JSONL count: 1,794 records / 1,794 ids.
- `SemanticMemoryFAISS.ingest_text()` and maintenance writers still exist.

Impact:

- Canonical promotion is possible, but direct write surfaces remain.

Recommendation:

- 11B should make `promote_record()` the governed promotion path and restrict direct production writes.

### GMTA-10C-005: Rooms state is active but not normalized enough for promotion decisions

Evidence:

- `memory/rooms` exists with 2 children.
- `tmp_agent/state/rooms` exists with 4 children.
- Current and legacy code references include hardcoded `C:/AI_VAULT` paths.

Impact:

- Rooms can support operational continuity, but cannot yet be treated as canonical semantic truth.

Recommendation:

- Normalize paths and add freshness/dedupe rules before relying on rooms for autonomous promotion.

### GMTA-10C-006: Direct semantic writers remain a governance gap

Evidence:

- `SemanticMemory.ingest_text()`, `ingest_many()`, `ingest_session_memory()`, `compact()`.
- `SemanticMemoryFAISS.ingest_text()`, `compact()`, `rebuild_index()`, `_save_index()`.

Impact:

- If exposed to routes or tools, direct writers can bypass future SCVL promotion checks.

Recommendation:

- Introduce explicit governance and caller restrictions around all writer APIs.

## Recommended Sequence

1. `FRONT-BRAIN-SESSION-MEMORY-ISOLATION-FIX-10D`
   - Make session memory artifacts session-scoped or lock/namespace-safe.
   - Preserve existing read behavior where possible.
   - Add tests for concurrent or mismatched session IDs.

2. `FRONT-BRAIN-SCVL-FINAL-ANSWER-GATE-11A`
   - Wire SCVL into the final visible answer path.
   - Fail closed or degrade with explicit warning when user constraints conflict with response/tool use.
   - Do not mutate memory.

3. `FRONT-BRAIN-SCVL-SEMANTIC-PROMOTION-GATE-11B`
   - Gate `promotion_candidate_promoter.py` and/or `SemanticMemoryFAISS.promote_record()`.
   - Make direct production promotion impossible without coherence validation and governance metadata.

4. `FRONT-BRAIN-E2E-AUTONOMY-MEMORY-TOOL-FALLBACK-11C`
   - End-to-end tests for final answer, tool evidence, memory reads, blocked writes, and fallback behavior.

5. `FRONT-BRAIN-OLLAMA-PROVIDER-CENTRALIZATION-11D`
   - Remove scattered provider endpoint definitions and ensure Kimi/Ollama routing is centrally governed.

6. `FRONT-BRAIN-ROUTER-MAIN-STRANGLER-12A`
   - Continue reducing `session.py` / `main.py` god-object risks after safety gates are in place.

## Do Not Do Next

Do not wire SCVL directly into semantic promotion before 10D.

Do not treat curated dry-run promotion as real semantic promotion.

Do not rebuild FAISS as part of this audit.

Do not modify `memory/semantic/*` as part of topology cleanup.

Do not rely on rooms as canonical semantic truth until path/freshness ownership is fixed.

## Commands Executed

Preflight:

```powershell
git fetch origin
git pull --ff-only origin codex/own-capital-sustainable-return
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/codex/own-capital-sustainable-return
git diff --name-status
git diff --cached --name-status
git status --short --untracked-files=all
```

Inventory and audit commands:

```powershell
git grep -n "validate_semantic_coherence\|dry_run_only\|promote_record\|memory/semantic\|semantic_memory\|faiss\|rooms\|curated\|GITHUB_TOKEN\|api.github.com"
```

AST summaries were run for:

```text
tmp_agent/brain_v9/core/session_memory_state.py
tmp_agent/brain_v9/core/semantic_memory.py
tmp_agent/brain_v9/core/semantic_memory_faiss.py
```

Targeted snippets were inspected for:

```text
tmp_agent/brain_v9/memory/promotion_candidate_promoter.py
tmp_agent/brain_v9/core/session_chat_metrics.py
tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py
```

Runtime metadata inventory was read without mutation for:

```text
memory/semantic/semantic_memory.jsonl
memory/semantic/semantic_memory_faiss_ids.json
memory/semantic/semantic_memory_faiss.index
tmp_agent/state/session_memory.json
memory/rooms
tmp_agent/state/rooms
```

## No-Touch Confirmation

This audit did not intentionally modify:

- runtime code
- `tmp_agent/brain_v9/core/session.py`
- `tmp_agent/brain_v9/main.py`
- `tmp_agent/brain_v9/core/session_memory_state.py`
- `tmp_agent/brain_v9/core/semantic_memory.py`
- `tmp_agent/brain_v9/core/semantic_memory_faiss.py`
- `memory/semantic/*`
- FAISS index files
- rooms state
- curated ingestion code
- SCVL code
- trading/QC/IBKR code
- `.env`

The only intended tracked artifact for this front is this audit report.
