# Trace Smoke — 08F2

## Run ID

`agv2_94773981084674d1` (from `/v2/chat/agent` schema smoke)

## Result

- Status: **PASS**
- `trace` is list: true
- Trace length: 2
- Token leak detected: false

## Checks

Searched trace content for:

- `AGENTV2_08F2_TEST_TOKEN`
- `AGENTV2_TEST_ADMIN_TOKEN_08F1`

Neither token was present in the trace payload.

## Conclusion

Trace contract satisfied and no secret leakage detected in this controlled smoke.
