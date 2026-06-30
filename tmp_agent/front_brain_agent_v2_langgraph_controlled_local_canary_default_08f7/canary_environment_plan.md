# Canary Environment Plan — FRONT-BRAIN-AGENT-V2-LANGGRAPH-CONTROLLED-LOCAL-CANARY-DEFAULT-08F7

## Purpose

Run a controlled local canary where LangGraph is treated as the default backend only inside an isolated shell/session by setting `AGENT_V2_BACKEND=langgraph`.

## Isolation rules

- Isolated shell/session only.
- Set `AGENT_V2_BACKEND=langgraph` only inside that shell.
- Do not persist `AGENT_V2_BACKEND` at Machine or User level.
- Do not edit `.env`.
- Do not edit source defaults.
- Do not change startup scripts permanently.
- Do not connect broker/trading/money actions.
- Do not mutate memory/semantic/FAISS.
- All probes must be read-only or smoke-test only.
- After canary, unset `AGENT_V2_BACKEND` and verify Native.

## Required PowerShell canary setup

```powershell
$env:AGENT_V2_BACKEND = "langgraph"
$env:BRAIN_ADMIN_TOKEN = "LOCAL_CANARY_ONLY_TOKEN"
```

## Required rollback

```powershell
Remove-Item Env:\AGENT_V2_BACKEND -ErrorAction SilentlyContinue
```

## Safety statement

This canary simulates local default behavior by environment override only. It does not modify code default.

## Canary scope

1. Runtime selection probe
2. Smoke test execution under LangGraph opt-in
3. Dashboard/trace read-only observation
4. Rollback verification

## Explicitly forbidden

- Source code modification
- Test modification
- Runtime patch
- Implementing `plan_run`/`pause_run`/`resume_run`/`cancel_run`
- Making LangGraph default in source
- Changing Native default
- Changing dashboard routes
- Changing frontend/static files
- Changing `api_security.py`
- Changing `main.py`
- Changing `api_adapter.py`
- Changing `native_runtime.py`
- Changing `langgraph_parity_runtime.py`
- Changing `response_normalizer.py`
- Touching memory/semantic files
- Touching FAISS/vector indexes
- Touching trading, IBKR, broker, strategy, portfolio, or risk files
- Touching `.env` or secrets
- Touching autonomous journal or promotion queues

## Phase result

PHASE 2 — Canary environment plan: **COMPLETED**

## Recorded

`2026-06-30T19:18:00+00:00`
