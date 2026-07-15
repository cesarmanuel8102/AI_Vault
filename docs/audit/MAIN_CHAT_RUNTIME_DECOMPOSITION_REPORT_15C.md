# FRONT-BRAIN-CHAT-RUNTIME-DECOMPOSITION-15C

Status: `COMPLETED_HELPER_EXTRACTION`

## Scope

15C decomposes deterministic helper logic from the legacy `POST /chat` runtime path while keeping the route in `tmp_agent/brain_v9/main.py`.

## Baseline

- Initial HEAD: `f7337fa`
- Initial `main.py` lines: `2918`
- Initial app endpoint count: `51`
- Initial `POST /chat` block lines: `483`
- Backup branch: `backup/main-chat-runtime-pre-15c-f7337fa`

## Extracted Helpers

Created `tmp_agent/brain_v9/core/chat_runtime_helpers.py` with pure helper functions:

- `looks_like_harmful_intrusion_request`
- `is_code_inspection_request`
- `should_scan_local_network`
- `should_attempt_local_network_tool`
- `has_pending_action_signal`
- `extract_pending_action_from_text`

These helpers do not import `main.py`, `session.py`, memory/semantic, FAISS, trading, HTTP clients, subprocess, uvicorn, or order execution code.

## Main Route Changes

`POST /chat` remains in `main.py`. The route now delegates three deterministic decisions to helper functions:

- offensive intrusion request guard
- local-network tool fastpath predicate
- pending-action signal and payload extraction

The PAD/GOD/auth flow, curated helper fastpath, trace emission, timeout behavior, Tool01 result handling, and `ChatResponse` return shape remain in `main.py`.

## Metrics

- Endpoint count before: `51`
- Endpoint count after: `51`
- `main.py` lines after: `2897`
- `POST /chat` block lines after: `456`
- Helper dependency count before in `POST /chat`: `0` extracted helper calls for these predicates/parsers
- Helper dependency count after in `POST /chat`: `4` imported helper calls
- Final line counts are recorded by the validation output for the implementing commit.

## Tests Added

- `tests/unit/test_chat_runtime_helpers_15c.py`
- `tests/contract/test_main_chat_runtime_decomposition_15c.py`

## Validation

The intended validation set:

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile tmp_agent/brain_v9/core/chat_runtime_helpers.py`
- `python -m py_compile tests/unit/test_chat_runtime_helpers_15c.py`
- `python -m py_compile tests/contract/test_main_chat_runtime_decomposition_15c.py`
- Direct scripts: `CHAT_RUNTIME_HELPERS_15C_OK`, `MAIN_CHAT_RUNTIME_DECOMPOSITION_15C_OK`
- New pytest set: `11 passed`
- Existing router split contracts from 12B through 15C: `185 passed`
- Nontrading Agent V2 regression block with the 15C contracts included: `203 passed, 3 skipped`
- CI-style direct hygiene scripts through 15C: passed

## No-Touch Confirmation

15C is not allowed to touch:

- `tmp_agent/brain_v9/core/session.py`
- `session_agent_route.py`
- `session_scvl_gate.py`
- `scvl_promotion_gate.py`
- `semantic_memory_faiss.py`
- `memory/semantic/*`
- FAISS files
- `tmp_agent/state/*`
- trading/risk/IBKR/QC files
- runtime journals, ledgers, snapshots

## Preparation For 15D

15C reduces the executable body of `POST /chat` without moving the route. This prepares 15D to move the remaining route wrapper to a router/service boundary with lower risk, because deterministic guards and pending-action parsing are now covered by direct unit and contract tests.
