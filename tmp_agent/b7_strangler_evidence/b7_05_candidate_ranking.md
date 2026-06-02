# B7-STRANGLER-05 — Candidate ranking

10 candidates evaluated against the strangler priority list (low risk, low coupling, no main.py mod, shim-preservable, real reduction, no circular import, no semantic change).

| ID | Block | Lines | Pure | Coupling | Risk | Reduction | Difficulty | Decision |
|---|---|---:|---|---|---|---|---|---|
| **C1** | `_sanitize_llm_chat_response` (1 staticmethod) | **80** | yes | none | LOW | 1.4 % | low | **SELECT** |
| C2 | `_fmt_*` bundle (17 classmethods) | 295 | yes | dispatcher only | LOW | 5.1 % | medium | runner-up |
| C3 | `_extract_*` + grounded helpers (4) | 103 | yes | low | LOW | 1.8 % | low-medium | defer |
| C4 | `_truncate_to_budget` + `_context_budget` | 87 | yes | low | LOW | 1.5 % | low | defer |
| C5 | `_prefers_no_tool_analysis` + `_has_explicit_tool_target` + `_sanitize_memory_content` | 67 | yes | none | LOW | 1.2 % | low | defer |
| C6 | `_format_action_value` + `_format_tool_result` | 66 | partly | tied to C2 dispatcher | MED | — | medium | defer (with C2) |
| C7 | `_should_use_compact_chat_prompt` + `_should_use_analysis_frontier` | 72 | mostly | reads cls constants | MED | 1.2 % | medium | defer |
| C8 | `SLASH_COMMANDS` dict | 32 | n/a | none | LOW | 0.6 % | low | defer (with `_cmd_*`) |
| C9 | `_render_*` (2 classmethods) | 116 | mostly | cls 1-3 | MED | 2.0 % | medium | defer |
| C10 | `_cmd_*` (31 methods) | 703 | no | heavy self.* | HIGH | 12 % | high | **reject for B7-05** |

## Selection — C1: `_sanitize_llm_chat_response`

**Why selected**

1. **100 % pure.** AST analysis confirmed `self_uses == 0`, `cls_uses == 0`. The method depends only on the `re` module via the `_re` alias and calls `re.compile`, `.search`, `.sub`, `str.splitlines`, `str.strip`, `str.lower`. No `BrainSession` state or class members touched.
2. **Single staticmethod.** Already decorated `@staticmethod`, so the shim collapses to a one-line re-binding: `_sanitize_llm_chat_response = staticmethod(sanitize_llm_chat_response)`.
3. **External consumers preserved through the shim.** `tmp_agent/brain_v9/main.py:1257` calls `session._sanitize_llm_chat_response(...)` (instance-attribute access on a `BrainSession`) — works unchanged because Python resolves the shim through the class. main.py is a protected file and **will not be modified**.
4. **Strong test safety net pre-existing.** Three test files exercise the function:
   - `tests/unit/test_brain_chat_hygiene.py`
   - `tests/unit/test_agent_ghost_completion_hardening.py`
   - `tests/unit/test_real_verification_tool_trace_required.py`
   - `tmp_agent/tests/core/test_session.py`
   Behavioral regressions surface automatically.
5. **Mirrors B7-02 / B7-03 / B7-04 strangler pattern** — extract pure logic into a small dedicated module, leave a re-export/shim on the original class, no runtime semantics change, fully reversible.
6. **No circular-import risk** — new module imports only `re`; `session.py` imports from it.
7. **No protected paths touched.** Productive change limited to `session.py` (in IMPLEMENT phase) plus one new module under `tmp_agent/brain_v9/core/`.

**Why not C2 (runner-up)**

C2 yields ~3.7× more reduction and is also genuinely pure, but it requires 17 individual classmethod shims to keep `getattr(cls, _TOOL_FORMATTERS[tool])` working. That is still strangler-compatible, just larger surface for review. Recommended as **B7-STRANGLER-06**.

**Why not C3-C9**

Either smaller reduction than C1 with comparable risk (C5), or moderate coupling that requires extra design decisions (C7 reads cls constants; C9 has cls. accesses; C3 path-resolution semantics). Better staged after C1+C2 set conventions.

**Why C10 is rejected for B7-05**

`_cmd_*` is the largest block (703 lines) but every handler has `self_uses` 1-12. The strangler principle demands small, surgical, low-risk extractions; pulling slash commands requires an entirely different design (delegate object or registry pattern) and a unit-test scaffold that does not yet exist. Revisit much later — likely after `chat`, `_route_to_agent`, and `_maybe_fastpath` have been decomposed.
