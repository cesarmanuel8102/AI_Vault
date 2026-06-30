# Token Security Smoke — 08F3

## Goal
Ensure the test admin token value is not leaked in any captured response payload or subprocess log.

## Results

| Check | Result |
|-------|--------|
| Backend chat response | No token value |
| Backend trace response | No token value |
| Backend health response | No token value |
| Dashboard chat response | No token value |
| Dashboard trace response | No token value |
| Dashboard health response | No token value |
| Backend stdout log | No token value |
| Backend stderr log | No token value |
| Dashboard stdout log | No token value |
| Dashboard stderr log | No token value |

## Notes
- The test token value does not appear in any response body or uvicorn log.
- Token names appear only as placeholders in report metadata; the actual value is not stored.
- The token was generated for this smoke only and is not a production secret.
