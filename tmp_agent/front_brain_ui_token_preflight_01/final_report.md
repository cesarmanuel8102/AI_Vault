# FRONT-BRAIN-UI-TOKEN-PREFLIGHT-01

Status: IMPLEMENTED_VALIDATED

Implemented:
- UI now blocks chat send before making /v2/chat/agent requests if no operator token is saved.
- UI focuses token input and shows explicit instruction to use the token printed by the local launcher.
- No token value is committed in UI source.
- Added 	ests/smoke/test_front_brain_ui_token_preflight_01.py.

Validation:
- python -m py_compile passed for smoke.
- Combined smoke set: 9 passed.

Safety:
- Strict operator access preserved.
- No hardcoded real token.
- No broker, real money, memory/semantic, FAISS, trading, or .env mutation.

Next recommended front: FRONT-BRAIN-CONTRACT-TESTS-BOUNDARIES-02.
