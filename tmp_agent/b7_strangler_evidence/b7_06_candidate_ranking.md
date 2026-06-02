# B7-STRANGLER-06-INVENTORY — Phase B: Candidate Ranking

10 candidates evaluated (≥7 required). Selection: **C1 — `_fmt_*` tool result formatters bundle**.

| Rank | ID | Candidate | Lines | Risk | Reduction est. | Notes |
|--:|---|---|--:|---|--:|---|
| **1** | **C1** | **`_fmt_*` (17 classmethods)** | **295** | **low** | **−244** | **PERFECT isolation; zero couplings; clean dispatcher** |
| 2 | C2 | `_format_tool_result` + `_format_action_value` + `_TOOL_FORMATTERS` | 87 | medium | −70 | extract AFTER C1 (B7-07) |
| 3 | C5 | grounded code helpers (`_extract_*`, `_build_*`, `_slice_lines`, `_find_test_references`) | 117 | low-medium | −100 | strong B7-07 candidate |
| 4 | C3 | `_render_*` operational summaries | 116 | medium | −110 | cls.* coupling |
| 5 | C2 | (see above, dispatcher) | — | — | — | — |
| 6 | C4 | `_truncate_*` + `_context_budget` | 94 | medium | −80 | mixed bundle (instance method tethers it) |
| 7 | C6 | query intent helpers (`_prefers_*`, `_has_explicit_*`, `_sanitize_memory_*`, etc.) | 76 | low | −60 | low cohesion across domains |
| 8 | C7 | `_should_use_compact_chat_prompt` + `_should_use_analysis_frontier` | 72 | medium | −55 | high cls.* coupling |
| 9 | C8 | static utilities (5 small) | 36 | low | −25 | too small/scattered |
| 10 | C9 | residual `_is_*` predicates | 65 | low | −45 | scattered, low ROI |
| 11 | C10 | `_cmd_*` (31 instance methods) | 703 | high | n/a | requires broad refactor; out of scope |

## Why C1 wins

- **Largest cleanly-isolated bundle in session.py** — 295 lines, 52% of all pure-modular surface.
- **Zero internal coupling**: all 17 methods have `self_uses_total=0`, `cls_uses_total=0`, no cross-`_fmt_*` calls.
- **Zero external repo callers** (verified via repo-wide scan).
- **Single dispatcher entry point** at `_TOOL_FORMATTERS`/`_format_tool_result` via `getattr(cls, name)` — preservable via same-arity classmethod shims.
- **Pre-identified by B7-05 inventory** as runner-up C2 (queued for "B7-06").
- **Lowest implementation risk per line moved** across all candidates.
