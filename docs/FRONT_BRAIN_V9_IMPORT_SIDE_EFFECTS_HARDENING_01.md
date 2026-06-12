# FRONT-BRAIN-V9-IMPORT-SIDE-EFFECTS-HARDENING-01

## Status
`IMPORT_TESTCLIENT_SIDE_EFFECT_GUARD_CREATED`

A controlled import of `tmp_agent.brain_v9.main` plus `TestClient(app)` did not produce tracked diffs and did not modify `tmp_agent/knowledge/external/github`.

This front records the guard as a regression smoke test so future imports cannot silently dirty curated GitHub knowledge JSON.

## Safety
- memory_mutated: `false`
- faiss_mutated: `false`
- trading_touched: `false`
- legacy_touched: `false`
