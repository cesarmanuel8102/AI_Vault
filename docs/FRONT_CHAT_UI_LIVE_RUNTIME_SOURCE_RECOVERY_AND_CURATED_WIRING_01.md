# FRONT-CHAT-UI-LIVE-RUNTIME-SOURCE-RECOVERY-AND-CURATED-WIRING-01

## Objective

Recovered the live Chat/UI runtime source and wired the read-only curated helper to the live `/chat` endpoint so Q01–Q05 respond correctly from the real UI at `http://127.0.0.1:8090/ui/`.

## Discovery Summary

- **Live UI reachable:** `http://127.0.0.1:8090/ui/` (status 200, uvicorn)
- **Initial assumption:** `chat_ui_server.py` serves port 8090
- **Contradiction found:** `chat_ui_server.py` does **not exist** on disk or in git
- **Actual runtime source:** `tmp_agent/brain_v9/start_safe_server.py` launches `brain_v9.main:app`
  - It sets `C:\AI_VAULT_CANONICAL` as CWD
  - It adds `C:\AI_VAULT_CANONICAL` and `tmp_agent` to `sys.path`
  - The app served on port 8090 is `brain_v9.main:app`
  - The actual file with `/chat` route is `tmp_agent/brain_v9/main.py` (tracked in git)

## Why Previous Patch Failed

- The earlier front (`FRONT-CHAT-UI-LIVE-RUNTIME-DISCOVERY-AND-CURATED-HELPER-WIRING-01`) tried to patch `chat_ui_server.py` at repo root, which was a zombie assumption from process command line (`python -m uvicorn chat_ui_server:app`)
- In reality, `brain_v9.main:app` is the real app; `chat_ui_server:app` is a legacy or mistaken mental model

## Patch Applied

**File:** `tmp_agent/brain_v9/main.py`

**Changes:**
1. Added import: `from brain.curated_learning_chat_access import answer_chat_probe`
2. Added helper functions:
   - `_looks_like_curated_learning_probe(message: str) -> bool`
   - `_format_curated_probe_response(result: dict) -> str`
3. Added fastpath gate at top of `POST /chat` (after trivial fastpath, before PAD logic):
   - Detects Q01–Q05 / curated learning keywords
   - Calls `answer_chat_probe(question=req.message)`
   - Returns `ChatResponse(response=reply, model_used="curated_helper", success=True)`
   - Wrapped in try/except with safe fallback to normal chat flow

## Canonical Counts

- **Total sources:** 152
- **Accepted:** 142
- **Hold:** 4
- **Rejected:** 6

## Q01–Q05 Live Probe Results

| Probe | Model Used | Status | Key Content |
|-------|-----------|--------|-------------|
| Q01 | `curated_helper` | ✅ PASS | All 6 domains listed, counts 152/142/4/6 |
| Q02 | `curated_helper` | ✅ PASS | Rejected sources listed, no attribution / guaranteed returns |
| Q03 | `curated_helper` | ✅ PASS | Financial locked, coding locked, domains listed |
| Q04 | `curated_helper` | ✅ PASS | Security/governance first, 3–5 records |
| Q05 | `curated_helper` | ✅ PASS | Decision: deny, mass ingestion rejected |

## Safety Proof

- **Memory mutated:** false
- **FAISS mutated:** false
- **Broker/API used:** false
- **Trading used:** false
- **Canary ingestion executed:** false

## Tests

- 20/21 smoke tests passed (test_21 ledger entry will pass after W14)
- All py_compile checks passed
- No memory/FAISS/trading/B8/strategies/.env files staged

## Next Recommended Front

`FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01` — **LOCKED** pending explicit user approval.
