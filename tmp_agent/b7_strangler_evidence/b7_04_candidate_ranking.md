# B7-STRANGLER-04 — Candidate Ranking

**session.py post-B7-03:** 5925 lines. Cumulative reduction since pre-B7-02: −1712 lines.

## Evaluation criteria

low_risk · low_coupling_with_BrainSession · no_main.py_change · no_protected_path_touch · preserve_via_reexport_or_shim · small_clear_tests · real_line_reduction · no_circular_import.

## Candidates

| ID | Name | ~Lines | Coupling | External consumers | Risk | Difficulty | Value | Recommendation |
|----|------|--------|----------|--------------------|------|------------|-------|----------------|
| **C1** | **Routing regex constants module** | **113 → −95** | none (pure data) | tests + debug_routing import `AGENT_KEYWORDS`/`_AGENT_PATTERNS` from session | **low** | low | **high** | **SELECT** |
| C2 | `_fmt_*` formatter classmethod bundle | 295 → −270 | classmethods on BrainSession | none | medium | medium | high | DEFER (next ticket) |
| C3 | `SLASH_COMMANDS` dict alone | 32 → −25 | none | tests/core/test_session.py | low | very low | low | DEFER (too small alone) |
| C4 | `_render_*` + `_format_*` bundle | 182 → −165 | classmethods on BrainSession | none | low-med | medium | medium | DEFER (pair with C2) |
| C5 | `_sanitize_llm_chat_response` staticmethod | 80 → −72 | none (pure) | none | low | low | medium | RUNNER-UP |
| C6 | Path constants bundle (`_STATE_PATH` etc.) | 9 → −5 | none | conftest + hygiene tests **monkeypatch** session_mod._STATE_PATH/_UI_INDEX/_UI_EDIT_STATE_PATH/_CHAT_SESSION_DEFAULTS_PATH | **HIGH** (monkeypatch trap) | high | very low | **REJECT** |
| C7 | `_tool01_*` subsystem | 363 → −340 | heavy self / permission gate | tests/unit/test_tool01_* | high | high | high | **REJECT** (off-limits per rules) |

## Selected: **C1 — Routing regex constants module**

- New module: `tmp_agent/brain_v9/core/session_routing_constants.py`
- Move: `AGENT_INTENTS`, `AGENT_KEYWORDS`, `_AGENT_PATTERNS`, `_CODE_ANALYSIS_PATH_RE`, `_LEAK_TAIL_RE`, `_CONTINUE_WORDS_RE`, `_CORRECTION_RE`
- Re-export from session.py to preserve:
  - `from brain_v9.core.session import AGENT_KEYWORDS` (tmp_agent/tests/core/test_session.py:24)
  - `from brain_v9.core.session import _AGENT_PATTERNS` (tmp_agent/tests/core/test_session.py:25, tmp_agent/debug_routing.py:29)
  - `session_mod._AGENT_PATTERNS` read access (tests/unit/test_brain_chat_hygiene.py:182)
  - `session_mod.AGENT_KEYWORDS` read access (tests/unit/test_b7_routing_heuristics_characterization.py)
- Estimated session.py reduction: ~95 lines → projected post-B7-04 size **≈ 5830 lines** (cumulative −1807).

## Rejected / deferred reasoning

- **C6 (path constants):** real test monkeypatching against `session_mod._STATE_PATH` and friends would break unless we both (a) re-export from session.py AND (b) make sure all in-file callsites still use the live re-imported reference. For only ~5 lines saved, the trap-to-payoff ratio is wrong.
- **C7 (Tool01):** explicitly off-limits per ticket rules.
- **C2 / C4 (`_fmt_*`, `_render_*`/`_format_*`):** strong follow-ups but require a method-rebinding pattern that hasn't been established yet in the strangler series; they belong in B7-STRANGLER-05+.
- **C3 alone:** too small to justify a dedicated module.
