# FRONT-BRAIN-CI-DASHBOARD-LIVE-CONTRACT-07

Status: IMPLEMENTED_VALIDATED

## Scope
Updated .github/workflows/nontrading-smoke-regression.yml so the gent-v2-boundaries job includes 	ests/smoke/test_front_brain_dashboard_api_live_contract_06.py.

The test is skip-safe for live-only sections when 8091/8092 are unavailable, while still retaining static dashboard/proxy checks.

## Validation
- py_compile: PASS
- Local CI-equivalent Agent V2 boundary set: 24 passed

## Safety
No real money, broker/IBKR, trading code, memory/semantic data, FAISS/index, .env, or secrets touched.
