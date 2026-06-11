# Chat Route Discovery Report

**Status**: LOCAL_CHAT_ROUTE_NOT_FOUND

## Findings

1. **No `app.post('/chat')`** found in any Python file in `brain/` or `tmp_agent/` directories.
2. **No `tmp_agent/brain_v9/core/session.py`** exists in this repository.
3. **FastAPI app found** only in `tmp_agent/advisor_server_clean.py` with `/v1/advisor/next` endpoint, not `/chat`.
4. **Chat references exist** only in audit JSONs (`b1_route_inventory.json`) and external probe scripts (`run_advanced_battery.py`, `run_bor4b_validation.py`).
5. **No local chat server process detected** on port `8090` or `8010`.

## Conclusion

The Chat/UI runtime lives **outside this repository** or in an **external environment** not tracked in `C:\AI_VAULT_CANONICAL`. This is a design/architecture constraint, not a failure.

## Resolution

Cannot apply a minimal runtime patch to a non-existent local file. Instead, the helper (`brain.curated_learning_chat_access`) must be imported by the **external chat runtime** when it exists.

## Adapter Provided

`brain/curated_learning_chat_access.py` is the canonical read-only helper that any external chat runtime can import.

```python
from brain.curated_learning_chat_access import answer_chat_probe, build_chat_safe_context
```

## Next Steps

- If an external chat runtime exists elsewhere, the operator must import `brain.curated_learning_chat_access` there.
- If a local chat runtime is created later, apply the patch at that time.
- This front proceeds with helper-only completion.
