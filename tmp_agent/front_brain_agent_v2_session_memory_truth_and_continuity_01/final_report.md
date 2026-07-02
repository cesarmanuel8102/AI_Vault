# Final Report — FRONT-BRAIN-AGENT-V2-SESSION-MEMORY-TRUTH-AND-CONTINUITY-01

**Status**: CLOSED
**Mode**: `read_only_with_conditional_finalizer_fix`
**HEAD**: `700b836a482a582365f786d47989e0943b0a9492`
**Branch**: `codex/own-capital-sustainable-return`
**Server state**: untouched (Brain PID 127900 on `:8091`, Dashboard PID 102348 on `:8092` — both left running unmodified)
**Commit**: NOT created — operator authorization required before staging any change

---

## Trigger recap

Agent V2 run `agv2_0ea89c34bea6a903` (2026-07-02T05:22:46Z, `dashboard_operator`, route `direct_assistant`) delivered a `final_answer` denying Brain's system-level persistent memory ("cada interacción es independiente y no queda escrito en ningún lugar persistente"). Operator verdict: **not acceptable**. Two clauses are truthful in isolation ("no tools were executed in this run"), but the surrounding text denies system capability, contradicting `AGENT_V2_IDENTITY_PREAMBLE` at `finalizer.py:22-36`.

---

## Answers to the five acceptance questions

### Q1 — Did this run use tools?
**No.** `executed_tools=[]`, `tools_considered=[]`, `memory_hits=[]`, `planner_used=false`, `planner_source="direct_assistant_short_circuit"`. Cited from `runs_parity/agv2_0ea89c34bea6a903/run.json:38,64,66,88,120`. The "No tools were executed in this run" prefix in the answer is truthful.

### Q2 — Does Brain have persistent memory as a system?
**Yes.** Verified live:
- `/brain-dashboard/safety`: `faiss_ids=1794`, `faiss_ntotal=1794`, `semantic_memory_lines=1794`, `canonical_semantic_mutated=true`.
- Last audited FAISS write: 2026-06-15 (per T1's own evidence answer at `agv2_78cfbf756847667a/run.json:90+`).
- Every chat turn creates `run.json` + `trace.jsonl` under `runs_parity/` (1150 entries, canonical store, last mtime 2026-07-02 05:22:46Z).

The system-level denial in the offending answer is factually false.

### Q3 — Can the previous question be recovered?
**Yes.** Reconstructed the full 3-turn history from `runs_parity/` for user `dashboard_operator`:

| Turn | UTC | run_id | goal | route |
|---|---|---|---|---|
| T1 | 05:21:03Z | `agv2_78cfbf756847667a` | "dime cuando fue la ultima escritura en tu memoria FAISS" | `brain_evidence` (conf 0.95) |
| T2 | 05:22:02Z | `agv2_808118600f5a90b4` | "y porque no se esta escribiendo en ella?" | `direct_assistant` (conf 0.5) |
| T3 | 05:22:46Z | `agv2_0ea89c34bea6a903` | "y porque no se esta escribiendo en ella? me refiero a la sesion o pregunta anterior." | `direct_assistant` (conf 0.5, offending) |

The runtime's OWN context path (`langgraph_parity_runtime._assemble_isolated_context` at L290-380 reading from `self.run_root=runs_parity/`) returns these turns correctly when simulated. The legacy `context_assembler.assemble_recent_context` at `context_assembler.py:12` reads from stale `runs/` (last write 2026-07-01 22:27) — this bug affects the pre-planner path only, not the finalizer path.

### Q4 — Why is memory not written automatically?
**By governance policy, not by accident.**
- `api_adapter.py:170-185` `/v2/agent/maintenance/modes` reports `semantic_faiss_writes_blocked=True`, `patch_apply_requires_approval=True`, `trading_blocked=True`.
- `langgraph_parity_runtime.py:578` sets `state["memory_gateway_read_only"]=True` on every run.
- The only sanctioned write path is the `promotion_candidate_promote` tool with `approval_required=True`.
- No conversation-turn → semantic memory auto-write pipeline exists.
- The front's own `hard_prohibitions` list at `front_spec.json:18-24` explicitly forbids adding one.

### Q5 — What is needed to activate safe conversational memory?
**Four repairs, in this order** (all OUT of this front's scope):

1. **Session-memory READ repair** (FRONT-B):
   - Fix `context_assembler.py:12` RUN_ROOT stale path.
   - Investigate and eliminate the twin-write pollution in `runs_parity/` (each turn currently writes two `run.json` variants — one with field `goal`, one with `message`).
   - Widen route-inheritance policy at `langgraph_parity_runtime.py:535-543` (currently only inherits for `brain_evidence`/`mixed_brain_reasoning`/`operational_agent`).
   - Consider whether `_memory_retrieval_node` at `langgraph_parity_runtime.py:575-580` should call `semantic_retrieve` for `direct_assistant` routes when a follow-up hint is detected.

2. **Expanded chat validation + evaluator denial rubric** (FRONT-A):
   - Replay the 3-turn trigger sequence.
   - Add follow-up battery.
   - Add an evaluator rubric that penalizes identity/memory denials — the current deterministic evaluator scored T3 at `full_parity_score=35/35` with `memory_retrieval_adequate=true` (false-positive).

3. **Approved memory-write pipeline** (FRONT-C):
   - Governed, approval-gated write path from conversation summaries into semantic memory.
   - Blocked until #1 and #2 confirm reads and identity are truthful.

4. **Conversation transcript persistence contract** (FRONT-D):
   - Transcripts ALREADY exist in `runs_parity/`.
   - Work needed: surface `run_id` back to client in `/v2/chat/agent` response contract, add `session_id`/`conversation_id`/`prev_run_id` fields to `AgentChatRequest` (currently forbidden by `extra='forbid'` at `api_adapter.py:63`).
   - Lowest priority because underlying storage is correct.

---

## In-scope fix applied

Per conditional authorization in `front_spec.json:25-30` (`condition_met=true` — the finalizer/response_normalizer WAS falsely denying memory), applied a **surgical, additive-only** patch to `response_normalizer.py`.

**Changes**:

| ID | Kind | Location | Detail |
|---|---|---|---|
| FIX_B.1 | Add regex patterns | `response_normalizer.py:198-215` | +10 patterns for memory/session-persistence denials (6 Spanish, 4 English) |
| FIX_B.2 | Extend replacement text | `response_normalizer.py:218-235, 237-254` | Append explicit memory-capability disclosure to `_IDENTITY_REPLACEMENT_ES` and `_IDENTITY_REPLACEMENT_EN` |

**NOT modified**: existing 13 patterns 1..13, `_identity_guard_rewrite` control flow, `normalize_agent_v2_chat_response` mount point, any file in `fix_touch_forbidden`.

**Pattern count**: 13 → 23 (+10).

---

## Verification (deterministic, offline)

Ran `_fix_verification.py` — replays the exact `final_answer` from `agv2_0ea89c34bea6a903/run.json:90` through both the OLD (reconstructed inline as `_OLD_PATTERNS`, 13 patterns) and NEW (imported live from patched module, 23 patterns) guards.

| Metric | OLD (before) | NEW (after) |
|---|---|---|
| Pattern count | 13 | 23 |
| Pattern matches on offending text | 1 | 5 |
| Matched pattern indices | [10] | [10, 13, 15, 16, 18] |
| Denial phrases leaked to user | **5** | **0** |
| `all_denial_phrases_removed_by_new` | — | **true** |
| Output length | 690 | 216 (pattern-only) / 1244 (full rewrite with new preamble) |

The five denial phrases tracked:
1. `sesión anterior` — removed by new pattern #15
2. `Cada interacción que tenemos es independiente` — removed by new pattern #13
3. `no queda escrito en ningún lugar persistente` — swallowed by pattern #13 match (same sentence)
4. `no existe una memoria de chat que persista` — removed by new pattern #16
5. `para mí es como empezar de nuevo` — removed by new pattern #18

**Full rewrite output** now prepends the memory-truthful preamble ("Brain SÍ tiene memoria persistente como sistema: el índice FAISS y la semantic memory conservan entradas indexadas, y cada turno de chat se escribe en runs_parity/..."). The 755-char denial-laden answer becomes a 1244-char truthful capability disclosure + residual harmless prose. Zero denial phrases survive.

Verification report: `_fix_verification.json` in this front dir.

---

## Recommended next-front ranking

**B → A → C → D**

1. **B: session_memory_read_repair** — fixes the FOUR compounding issues (RUN_ROOT stale, twin-write, narrow inheritance, memory_retrieval_node bypass) that caused context loss on T2/T3 in the first place. Highest impact because it repairs the root cause of the context-loss chain, not just the finalizer symptom.

2. **A: expanded_chat_validation** — after B, replay this trigger sequence and add a battery of follow-up patterns to confirm no regression. Adds evaluator denial rubric to prevent future false-positive scoring.

3. **C: approved_memory_write_pipeline** — only meaningful once B+A confirm reads and identity are truthful. Governed write path with approval gate.

4. **D: conversation_transcript_persistence** — mostly documentation/contract work since transcripts already persist. Lowest priority; can be folded into A if desired.

---

## Hard-prohibitions checklist

- [x] No memory / semantic / FAISS edits — only READ endpoints touched for state snapshot
- [x] No auto-write implementation
- [x] No R2 start
- [x] No roadmap continuation
- [x] No expanded validation — only deterministic simulation on the single offending answer
- [x] No touch to `context_assembler.py`, `_memory_retrieval_node`, `trading/*`, `api_security.py`, `start_local_browser_operational.py`
- [x] Server state untouched (Brain 8091, Dashboard 8092 both left running)
- [x] Three previously parked issues remain parked (stale PID file, dashboard crash root cause unknown, scratch file cleanup)

---

## Closeout

**Front status**: CLOSED
**Commit created**: NO (operator authorization required)
**Working tree state**: `response_normalizer.py` modified (uncommitted), plus 5 new files in this front dir.

**Next action required from operator**:
1. Review `_evidence_pack.md`, `_fix_verification.json`, and this report.
2. Decide whether to authorize commit of `response_normalizer.py` change.
3. Decide whether to open **FRONT-B: session_memory_read_repair** as the next front.

## Artifacts written by this front

- `front_spec.json` — front definition
- `_evidence_pack.md` — full evidence with file:line citations, discovery narrative
- `_fix_verification.py` — deterministic before/after verifier
- `_fix_verification.json` — verifier output
- `final_report.json` — machine-readable closeout
- `final_report.md` — this file

## Source file modified (uncommitted)

- `tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py` — additive-only. Patterns 13→23. Replacement text extended with memory-capability disclosure.
