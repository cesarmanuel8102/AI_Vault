# FRONT-BRAIN-DASHBOARD-API-LIVE-CONTRACT-06

Status: IMPLEMENTED_VALIDATED

## Browser limitation
The in-app browser automation rejected direct control of http://127.0.0.1:8092/ under its security policy. I did not attempt to bypass that restriction. Validation proceeded through reproducible HTTP/API live checks plus static UI/proxy checks.

## Scope
Added 	ests/smoke/test_front_brain_dashboard_api_live_contract_06.py.

## What is covered
- Dashboard static files do not expose the operator token literal.
- Dashboard JS uses /brain-dashboard/chat and does not send X-Brain-Token from client JS.
- Dashboard 8092 health is live.
- Dashboard /brain-dashboard/agent-v2/status reports canonical Agent V2 / LangGraph parity / Kimi.
- Dashboard /brain-dashboard/chat proxies to canonical /v2/chat/agent.
- Dashboard trace proxy fetches run trace by un_id.
- Direct Brain /v2/chat/agent rejects missing token with HTTP 403.

## Validation
- py_compile: PASS
- live dashboard/API smoke: 4 passed
- combined Agent/dashboard regression: 15 passed

## Safety
No real money, broker/IBKR, trading code, memory/semantic data, FAISS/index, .env, or secrets touched.
