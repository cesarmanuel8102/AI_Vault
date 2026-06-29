:# FRONT-BRAIN-DASHBOARD-CHAT-MANUAL-LIVE-SMOKE-AFTER-08E-R2 — Service Startup Notes

## Ports and processes
| Service | Port | Started | PID | Pre-existing |
|---------|------|---------|-----|--------------|
| Brain V9 backend | 8091 | yes | 75624 | no |
| Dashboard | 8092 | yes | 43228 | no |
| Isolated langgraph env backend | 8093 | yes | 45652 | no |
| Isolated invalid_backend env backend | 8094 | yes | 128860 | no |

## Startup commands
- Backend: `python -m uvicorn tmp_agent.brain_v9.main:app --host 127.0.0.1 --port 8091`
- Dashboard: `python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092`
- Working directory: `C:\AI_VAULT_CANONICAL`
- `PYTHONPATH` included repo root.
- `BRAIN_ADMIN_TOKEN=LIVE_SMOKE_R2_TEST_ADMIN_TOKEN` set for backend strict-operator endpoints.

## Log files
- `tmp_agent/front_brain_dashboard_chat_manual_live_smoke_after_08e_r2/logs/brain_8091.log`
- `tmp_agent/front_brain_dashboard_chat_manual_live_smoke_after_08e_r2/logs/brain_8091.err`
- `tmp_agent/front_brain_dashboard_chat_manual_live_smoke_after_08e_r2/logs/dashboard_8092.log`
- `tmp_agent/front_brain_dashboard_chat_manual_live_smoke_after_08e_r2/logs/dashboard_8092.err`

## Restrictions respected
- No Docker started.
- No brokers started.
- No trading services started.
