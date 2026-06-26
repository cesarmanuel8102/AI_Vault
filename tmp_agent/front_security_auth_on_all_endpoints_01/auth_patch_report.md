# Auth Patch Report — FRONT-SECURITY-AUTH-ON-ALL-ENDPOINTS-01

## Protected Endpoints

All protected endpoints now require strict operator access (BRAIN_ADMIN_TOKEN):

| Endpoint | Protected? | Auth Dependency | Unauthenticated | Authenticated |
|----------|------------|------------------|----------------|---------------|
| POST /v2/chat/agent | Yes | require_strict_operator_access | 403 Forbidden | 200 OK |
| POST /v2/agent/runs | Yes | require_strict_operator_access | 403 Forbidden | 200 OK |
| POST /v2/agent/runs/{run_id}/plan | Yes | require_strict_operator_access | 403 Forbidden | 403 (run not found) |
| POST /v2/agent/runs/{run_id}/execute | Yes | require_strict_operator_access | 403 Forbidden | 403 (run not found) |
| POST /v2/agent/runs/{run_id}/pause | Yes | require_strict_operator_access | 403 Forbidden | 403 (run not found) |
| POST /v2/agent/runs/{run_id}/resume | Yes | require_strict_operator_access | 403 Forbidden | 403 (run not found) |
| POST /v2/agent/runs/{run_id}/cancel | Yes | require_strict_operator_access | 403 Forbidden | 403 (run not found) |
| POST /v1/chat/completions | Yes | require_strict_operator_access | 403 Forbidden | 200 OK |

## Unauthenticated Behavior

Requests without X-Brain-Token header return 403 Forbidden.

Requests with invalid token also return 403 Forbidden.

No localhost bypass is applied to these critical endpoints.

## Authenticated Behavior

Requests with valid BRAIN_ADMIN_TOKEN return 200 OK for valid requests.

Read_only mode gates remain in place and block write tools.

## Remaining Unauthenticated Endpoints

No remaining unauthenticated endpoints can create, plan, or execute tools.

Status/capabilities endpoints remain open for monitoring purposes.

## Localhost Bypass

Localhost bypass is NOT applied to protected endpoints.

Strict token auth is enforced.

## How Operator Should Call Local Endpoint Now

Example curl:

curl -i -X POST http://127.0.0.1:8091/v2/chat/agent \
  -H "Content-Type: application/json" \
  -H "X-Brain-Token: YOUR_BRAIN_ADMIN_TOKEN" \
  -d '{"message": "hello", "mode": "read_only", "user_id": "local"}'

## Tests Passed

- All 14 auth endpoint tests passed
- Memory git hygiene tests passed
- 08F batch promotion tests passed
- 08B promotion tool tests passed
- Semantic retrieval hygiene tests passed
- FAISS rebuild hydration tests passed
