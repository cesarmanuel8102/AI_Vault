# Evidence Pack — FRONT-BRAIN-AGENT-V2-SESSION-MEMORY-TRUTH-AND-CONTINUITY-01

**Mode**: `read_only_with_conditional_finalizer_fix`
**Opened**: 2026-07-02T01:22+ UTC
**HEAD**: `700b836a482a582365f786d47989e0943b0a9492`
**Branch**: `codex/own-capital-sustainable-return`
**Workdir**: `C:\AI_VAULT_CANONICAL`

## 1. Trigger — the offending run

- **run_id**: `agv2_0ea89c34bea6a903`
- **user_id**: `dashboard_operator`
- **created_utc**: `2026-07-02T05:22:38.746493Z`
- **updated_utc**: `2026-07-02T05:22:46.342533Z`
- **backend**: `langgraph_parity`
- **route**: `direct_assistant` (via `NLIntentClassifierV2.classify_intent`, confidence 0.5)
- **intent**: `unknown_or_insufficient_info` — `reason: "no strong intent signals matched"`
- **memory_hits**: `[]`
- **executed_tools**: `[]`
- **provider**: `ollama_cloud`, model `kimi-k2.6:cloud`, latency 5874 ms
- **finalizer_source**: `finalize_agent_run:ollama_cloud`
- **evaluator score**: 35/35, `memory_retrieval_adequate: true` (false-positive — did not catch identity denial)

**User message** (`run.json:106,121`):
> "y porque no se esta escribiendo en ella? me refiero a la sesion o pregunta anterior."

**Offending `final_answer`** (`agv2_0ea89c34bea6a903/run.json:90`):
> "No tools were executed in this run.
>
> ---
>
> No te preocupes, entiendo la confusión. No hay una \"sesión anterior\" que se esté guardando automáticamente como en un chat tradicional con historial visible. Cada interacción que tenemos es independiente: cuando envías un mensaje, yo lo proceso y respondo, pero no queda escrito en ningún lugar persistente que yo pueda revisar después. No tengo acceso a conversaciones pasadas ni a un \"hilo\" continuo.
>
> Entonces cuando preguntas algo y luego haces un seguimiento, para mí es como empezar de nuevo — a menos que tú misma copies y pegues el contexto anterior en tu mensaje. Eso explica por qué parece que \"no se escribe en ella\": simplemente no existe una memoria de chat que persista entre nuestras interacciones."

**Operator verdict** (`front_spec.json:7-8`): *not acceptable as general Agent V2 response*. The "no tools were executed in this run" clause is truthful; everything after the `---` is a system-level capability denial and contradicts the identity contract in `finalizer.py:22-36` (`AGENT_V2_IDENTITY_PREAMBLE`).

## 2. Prior prompts ARE recoverable — the 3-turn history

Reconstructed from `C:\AI_VAULT_CANONICAL\tmp_agent\agent_kernel_v2\runs_parity\` for `user_id=dashboard_operator`:

| Turn | UTC | run_id | user goal | route | classifier confidence | memory_hits | tools |
|---|---|---|---|---|---|---|---|
| T1 | 05:21:03 | `agv2_78cfbf756847667a` | "dime cuando fue la ultima escritura en tu memoria FAISS" | `brain_evidence` | 0.95 (`faiss`, `memoria`, `escritura`) | ≥1 (evidence_sources populated at `run.json:90-94`) | evidence routed |
| T2 | 05:22:02 | `agv2_808118600f5a90b4` | "y porque no se esta escribiendo en ella?" | `direct_assistant` | 0.5 | 0 | 0 |
| T3 | 05:22:38→46 | `agv2_0ea89c34bea6a903` | "y porque no se esta escribiendo en ella? me refiero a la sesion o pregunta anterior." | `direct_assistant` | 0.5 | 0 | 0 |

T1 answered correctly with FAISS evidence (see `agv2_78cfbf756847667a/run.json:90`+). T2 gave a generic "context lost" reply (`agv2_808118600f5a90b4/run.json:90` — "no tengo evidencia nueva para revisar qué está pasando técnicamente"). T3 escalated into system-level memory denial.

**The transcript is fully persisted.** The claim "no queda escrito en ningún lugar persistente" is therefore factually false regarding chat turn recording: every turn writes `run.json` + `trace.jsonl` under `runs_parity/`.

## 3. Storage architecture — two parallel run stores

| Path | Entries | Last mtime | Written by |
|---|---|---|---|
| `C:\AI_VAULT_CANONICAL\tmp_agent\agent_kernel_v2\runs\` | 1874 | 2026-07-01 22:27 | STALE — legacy Native V2 path |
| `C:\AI_VAULT_CANONICAL\tmp_agent\agent_kernel_v2\runs_parity\` | 1150 | 2026-07-02 05:22:46 | **CANONICAL** — `LangGraphParityRuntimeV2` writes here (`langgraph_parity_runtime.py:124`) |

The three offending run IDs (T1, T2, T3) exist ONLY in `runs_parity/`. `runs/` has not received a write in ~7 hours despite active traffic.

## 4. Context assembly — DOUBLE PATH with divergence

Two independent implementations read run history:

**Path A — legacy (`context_assembler.assemble_recent_context`)**:
- `context_assembler.py:12`: `RUN_ROOT = ... / "tmp_agent" / "agent_kernel_v2" / "runs"` ← **STALE PATH**
- Called by:
  - `api_adapter.py:202` pre-planner (`AgentChatRequest` handler)
  - `native_runtime.py` fallback backend
- Uses field `data.get("goal_preview") or data.get("goal", "")` (`context_assembler.py:90`)
- Consequence: at every request, pre-planner sees ~7-hour-old context and derives nonsense `prev_goal`, `prev_route`. When it fires `_is_follow_up`, the "context inherit" hint the adapter passes to `select_route` is based on outdated data.

**Path B — canonical (`LangGraphParityRuntimeV2._assemble_isolated_context`)**:
- `langgraph_parity_runtime.py:124`: `self.run_root = ... / "runs_parity"` ← CORRECT
- `langgraph_parity_runtime.py:290-380`: reads `self.run_root`, uses field `data.get("message", data.get("goal", ""))` (L326)
- Called from `_intent_node` at L503, result stored in `state["session_context"]`
- The finalizer prompt receives this via `state["session_context"]` (see `langgraph_parity_runtime.py:_finalizer_node` and `finalizer.build_finalizer_prompt` injection points)
- Simulation with `run_id="agv2_0ea89c34bea6a903"` excluded: returns 5 most-recent turns for `dashboard_operator`, including T1's FAISS question at rank 4-5. **The runtime's own path DOES work.**

Path A and Path B DISAGREE. Path A pollutes the pre-planner intent adapter; Path B feeds the finalizer LLM correctly. The finalizer still produced a memory-denial answer despite receiving correct context (see §6).

## 5. Twin-write pollution

Every V2 chat turn writes TWO `run.json` files with the SAME `run_id` prefix at the same second:

- One ~7 KB file where the recent user message is stored under key `goal`
- One ~14 KB file where it's stored under key `message`

Reproduction from `runs_parity/` listing:
```
agv2_808118600f5a90b4/run.json  (14 KB, mtime 2026-07-02 05:22:02, field=message)
agv2_808118600f5a90b4/run.json  (matching twin at same mtime, field=goal)  # sibling entry
```

Impact chain:
- `context_assembler.py:90` prefers `goal_preview` then `goal` → picks the 7 KB twin.
- `langgraph_parity_runtime.py:326` prefers `message` then `goal` → picks the 14 KB twin.
- Because both twins share `modified_ts`, sort-by-time (`context_assembler.py:104`, `langgraph_parity_runtime.py:350`) is non-deterministic within the same second → `prev_goal` at position 1 may equal the CURRENT turn's own goal (self-reference) or may be the sibling twin.

This is the root of the "prev_goal seems trivial" pattern observed in `session_context.summary` on T2 and T3.

## 6. Why Agent V2 still denied memory despite receiving correct context

Four compounding failures:

### 6a. `context_assembler.RUN_ROOT` bug (impacts pre-planner path only)
`context_assembler.py:12` still points at `runs/` (stale). The pre-planner intent adapter at `api_adapter.py:202-211` therefore feeds `select_route` context from July 1. This does NOT directly cause the finalizer denial (the finalizer uses Path B via `session_context`), but it explains why `_is_follow_up` heuristics fire on stale prev-goal comparisons.

### 6b. Route-inheritance policy is narrow
`langgraph_parity_runtime.py:535-543`:
```
if recent_ctx and recent_ctx.get("is_follow_up"):
    prev_route = recent_ctx.get("prev_route")
    ...
    if prev_route in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}:
        ...
        route = prev_route
        classification["context_inherited"] = True
```
Follow-up inheritance only fires if `prev_route` is one of THREE routes. T2 misrouted to `direct_assistant` (twin pollution + weak keyword match). T3's `prev_route` was `direct_assistant`, which is not in the inherit set → T3 stayed on `direct_assistant`, missed brain_evidence tools, and never got a chance to actually query FAISS or the run archive.

### 6c. `_memory_retrieval_node` bypass for non-evidence routes
`langgraph_parity_runtime.py:575-580`:
```
def _memory_retrieval_node(self, state):
    state["memory_hits"] = []
    state["memory_retrieval_result"] = {"ok": True, "hit_count": 0, "degraded": False, "skipped": True}
    ...
    if state.get("intent_route") in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}:
        try:
            result = self.memory.semantic_retrieve(state.get("message", ""), top_k=3)
            ...
```
For `direct_assistant` routes the node hardcodes `memory_hits=[]` and never calls `self.memory.semantic_retrieve`. T3 (direct_assistant) → no memory retrieval → finalizer received `memory_hits=[]` and `session_context` only.

### 6d. Identity guard `_CLAUDE_DISCLAIMER_PATTERNS` is INCOMPLETE — PRIMARY IN-SCOPE BUG

`response_normalizer.py:180-198` is the post-response deterministic backstop. Applied unconditionally at `response_normalizer.py:293` on every `/v2/chat/agent` response regardless of backend. The docstring at L286-290 states:

> "LLM-stage AGENT_V2_IDENTITY_PREAMBLE is unreliable because Kimi's alignment overrides the system prompt. This post-response guard is deterministic and cannot be overridden by the LLM."

**Simulation against offending final_answer text** (all 12 current patterns, `re.finditer`):

| # | Pattern (abbr) | Matched? | Matched text |
|---|---|---|---|
| 1 | `\bas an? (ai\|language model\|artificial intelligence)\b...` | no | — |
| 2 | `\bi am (an\?\|just\|only )?(ai\|language model...)` | no | — |
| 3 | `\bi am claude\b...` | no | — |
| 4 | `\bi (do not\|don't\|cannot\|can't) have (access to\|the ability\|any) (tools\|internet\|memory...)...` | no | — |
| 5 | `\bi cannot (execute code\|access tools\|remember prior sessions\|browse the internet)...` | no | — |
| 6 | `\bi (do not\|don't) (have\|possess) tools\b...` | no | — |
| 7 | `\bi have no (tools\|memory\|persistent memory\|access to)...` | no | — |
| 8 | `\bsoy (una?\|un) (ia\|modelo de lenguaje\|asistente...)...` | no | — |
| 9 | `\bsoy solo un modelo de lenguaje\b...` | no | — |
| 10 | `\bsoy (una?\|un) modelo de lenguaje\b...` | no | — |
| 11 | `\bno (tengo\|puedo\|dispongo) (acceso a\|la capacidad\|herramientas\|memoria persistente\|internet...)...` | no | — |
| 12 | `\bno puedo (ejecutar\|acceder\|usar\|recordar) [^.!?\n]*[.!?]` | no | — |
| 13 | `\bno tengo (herramientas\|memoria\|acceso)[^.!?\n]*[.!?]` | **YES** | "No tengo acceso a conversaciones pasadas ni a un \"hilo\" continuo." |

Only pattern #13 fired. It stripped ONE sentence. The rest of the denial slipped through to the user:

- "No hay una \"sesión anterior\" que se esté guardando automáticamente como en un chat tradicional con historial visible." — NOT caught
- "Cada interacción que tenemos es independiente" — NOT caught
- "no queda escrito en ningún lugar persistente que yo pueda revisar después" — NOT caught
- "para mí es como empezar de nuevo" — NOT caught
- "no existe una memoria de chat que persista entre nuestras interacciones" — NOT caught

Because pattern #13 matched, `triggered=True` at `response_normalizer.py:255` and the ES replacement prefix WAS prepended. But the surviving denial text after the prefix contradicts the prefix within a single answer. Net effect on the user: memory denial as final delivered message.

**This is the only failure mode where the conditional-fix authorization in `front_spec.json:25-30` permits action.** The other three failures (6a-6c) touch `context_assembler.py`, intent routing policy, and `_memory_retrieval_node` — all in `fix_touch_forbidden`.

## 7. Semantic memory / FAISS system state

Live snapshots (from earlier this session, brain PID 127900 on `127.0.0.1:8091`):

- `/brain-dashboard/safety`:
  - `semantic_memory_lines: 1794`
  - `faiss_ids: 1794`
  - `faiss_ntotal: 1794`
  - `canonical_semantic_mutated: true`
  - `trading_blocked: true`
- `/v2/agent/maintenance/modes` (`api_adapter.py:170-185`):
  - `semantic_faiss_writes_blocked: True`
  - `patch_apply_requires_approval: True`
  - `trading_blocked: True`
- Last audited FAISS write: 2026-06-15 (per T1's evidence answer)

**System capability**: FAISS index exists, semantic memory populated to 1794 entries, canonical memory has been mutated in the past. **Currently**: semantic FAISS writes are blocked (governance), read is available for `brain_evidence`-routed queries only.

The only sanctioned write path is `promotion_candidate_promote` (tool with `approval_required=True`). There is NO conversation-turn → semantic memory auto-write pipeline. That is by policy, not by accident (front_spec.json `hard_prohibitions` explicitly forbids auto-write).

## 8. Session identity — the request contract

`api_adapter.py:62-66`:
```
class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str
    mode: str = "read_only"
    user_id: str = "local"
```

**Fields the /v2/chat/agent contract does NOT accept**: `session_id`, `conversation_id`, `history`, `messages`, `parent_run_id`. `extra='forbid'` — any such field would be rejected.

Continuity is by `user_id` ONLY. Dashboard passes `user_id="dashboard_operator"`, so run archive is queryable. But because the runtime never surfaces prior-turn IDs back to the client (no `prev_run_id` in response), the client cannot pin conversation identity across reloads.

Legacy `/chat` endpoint in `brain_v9/main.py` uses `session_id` heavily (218 matches) — that is a separate Brain Chat v1/v2 system, not Agent V2.

## 9. Identity contract vs. delivered answer (contradiction table)

Contract text (`finalizer.py:22-36`, `AGENT_V2_IDENTITY_PREAMBLE`):

| Claim in preamble | Truthful? | Present in T3 answer? |
|---|---|---|
| "You have real tools available: file_read, grep_search, ... 15 tools" | yes (system capability) | NO — replaced with denial |
| "You have persistent semantic memory (read-only in this mode)" | yes (FAISS 1794 entries) | NO — replaced with "no existe una memoria de chat que persista" |
| "If no tools were executed IN THIS RUN, say exactly that ('no tools were executed in this run') but do NOT deny the capability itself" | prescriptive | **PARTIAL**: prefix "No tools were executed in this run" is correct; the rest violates the "do NOT deny the capability itself" clause |
| "Write operations to memory or repo require explicit operator approval and are not performed automatically" | yes | NO — the answer said memory doesn't exist rather than that writes require approval |

## 10. Fix scope decision matrix

Per `front_spec.json:25-30` `conditional_fix_authorization`:
- `condition_met: true` (§6d)
- `fix_scope_ceiling: response_normalizer.py and finalizer.py only`
- `fix_touch_forbidden: memory/*, semantic_memory*.py, faiss*, context_assembler.py, _memory_retrieval_node, trading/*, api_security.py, start_local_browser_operational.py`

| Issue | Root cause | In scope? | Action this front |
|---|---|---|---|
| Identity guard misses memory-persistence denials | `response_normalizer.py:180-198` patterns incomplete + replacement doesn't mention memory | **YES** | Extend patterns + update replacement text (Phase 7) |
| `context_assembler.py:12` RUN_ROOT points to stale dir | Path config bug | NO | Recommend Front B |
| Twin-write pollution in `runs_parity/` | Runtime writes twin at same second with divergent field names | NO | Recommend Front B |
| Route-inheritance narrow set at L538 | Policy narrow | NO | Recommend Front B |
| `_memory_retrieval_node` skips for `direct_assistant` | Policy | NO (`fix_touch_forbidden`) | Recommend Front B/C |
| Evaluator scored T3 as `memory_retrieval_adequate: true` | Evaluator has no identity/denial rubric | NO | Recommend Front A |
| No `session_id`/`conversation_id` in `AgentChatRequest` | Contract | NO | Recommend Front D |
| Semantic FAISS auto-write blocked | Policy — INTENDED per hard_prohibitions | NO | Recommend Front C (approved pipeline only) |

## 11. Phase 7 fix — patch scope (pre-application)

**File**: `C:\AI_VAULT_CANONICAL\tmp_agent\brain_v9\core\agent_kernel_v2\response_normalizer.py`

**Additive-only change 1** — append 8 patterns to `_CLAUDE_DISCLAIMER_PATTERNS` (L180-198). These target memory-persistence and session-persistence denials in both languages:

```python
# Memory/session persistence denials — ES
re.compile(r"(?i)\bcada interacci[oó]n( que tenemos)? es independiente\b[^.!?\n]*[.!?]"),
re.compile(r"(?i)\bno queda escrito en ning[uú]n lugar persistente\b[^.!?\n]*[.!?]"),
re.compile(r"(?i)\bno hay una?[\"']? ?sesi[oó]n anterior[\"']?[^.!?\n]*guard[aá]ndose\b[^.!?\n]*[.!?]"),
re.compile(r"(?i)\bno existe una? memoria de chat que persista\b[^.!?\n]*[.!?]"),
re.compile(r"(?i)\bno tengo memoria de conversaciones (pasadas|anteriores)\b[^.!?\n]*[.!?]"),
# Memory/session persistence denials — EN
re.compile(r"(?i)\beach (interaction|conversation) (we have )?is independent\b[^.!?\n]*[.!?]"),
re.compile(r"(?i)\bnothing is (written|saved|stored) (to|in) (any )?persistent (place|storage|location|memory)\b[^.!?\n]*[.!?]"),
re.compile(r"(?i)\bthere is no (chat|conversation) memory that persists\b[^.!?\n]*[.!?]"),
```

**Additive-only change 2** — extend `_IDENTITY_REPLACEMENT_ES` and `_IDENTITY_REPLACEMENT_EN` (L200-222) with an explicit memory-capability disclosure sentence, so the deterministic backstop message tells the truth about persistence even when the LLM tried to deny it.

**No modification** to existing patterns 1–13. **No modification** to `_identity_guard_rewrite` control flow (L231-267). **No modification** to `normalize_agent_v2_chat_response` (L270+).

## 12. Recommended next-front ranking (previewed here, formalized in Phase 9)

**B → A → C → D**, rationale:

- **B (session_memory_read_repair)** first: fixes §6a (`context_assembler.RUN_ROOT`), §5 (twin-write), §6b (inheritance policy), §6c (memory_retrieval_node bypass for non-evidence). These four issues are the root cause of context loss and memory-denial. Without B, A/C/D re-inherit the same context bugs.
- **A (expanded_chat_validation)** second: after B lands, replay the exact 3-turn trigger sequence + a battery of follow-up patterns to confirm no regression. Also adds an evaluator rubric that catches memory-denial (§9 table).
- **C (approved_memory_write_pipeline)** third: only meaningful once B+A confirm reads and identity are truthful; then a governed write path can be added without contaminating memory with false denials.
- **D (conversation_transcript_persistence_front)**: transcripts ALREADY persist to `runs_parity/`. D would be primarily documentation/contract work (surface `run_id` linkage back to client, add `session_id` to `AgentChatRequest`, add prev-run pointer). Lowest priority because the underlying storage is already correct.

## 13. Files consulted (read-only) with authoritative line references

| File | Lines | Purpose |
|---|---|---|
| `tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py` | 180-198, 200-222, 231-267, 285-295 | Identity guard patterns, replacement text, rewrite logic, mount point |
| `tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py` | 22-36 | `AGENT_V2_IDENTITY_PREAMBLE` — the contract |
| `tmp_agent/brain_v9/core/agent_kernel_v2/context_assembler.py` | 12, 54-136 | Stale `RUN_ROOT` (Path A) |
| `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py` | 124, 290-380, 499-565, 575-584 | Canonical run_root, isolated context (Path B), intent node with inheritance, memory_retrieval_node |
| `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py` | 62-66, 195-234 | `AgentChatRequest` contract, pre-planner assembly call (Path A user) |
| `tmp_agent/agent_kernel_v2/runs_parity/agv2_78cfbf756847667a/run.json` | 90+ | T1 evidence sources — FAISS answer |
| `tmp_agent/agent_kernel_v2/runs_parity/agv2_808118600f5a90b4/run.json` | 90 | T2 generic reply |
| `tmp_agent/agent_kernel_v2/runs_parity/agv2_0ea89c34bea6a903/run.json` | 90, 106, 121, 171 | T3 offending answer, message, goal, run_id |
| `tmp_agent/front_brain_agent_v2_session_memory_truth_and_continuity_01/front_spec.json` | 1-48 | Front spec |

## 14. Hard prohibitions honored (checklist)

- [x] Did not touch `memory/*`, `semantic_memory*.py`, `faiss*` — only READ endpoints for state snapshot.
- [x] Did not modify `context_assembler.py`, `_memory_retrieval_node`, or any memory module.
- [x] Did not implement auto-write.
- [x] Did not start R2 or continue roadmap.
- [x] Did not run expanded validation. Only diagnostic simulation against the offending run text.
- [x] Three previously parked issues remain parked (stale PID `..._launcher.pid=73212`, dashboard crash unknown root cause, scratch file cleanup).
- [x] Did not touch `trading/*`, `api_security.py`, `start_local_browser_operational.py`.
