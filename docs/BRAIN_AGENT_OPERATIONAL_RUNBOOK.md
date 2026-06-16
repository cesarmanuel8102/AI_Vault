# Brain Agent Operational Runbook

Start 8091 from `C:/AI_VAULT_CANONICAL`: `set PYTHONPATH=C:/AI_VAULT_CANONICAL/tmp_agent;C:/AI_VAULT_CANONICAL && python -m uvicorn brain_v9.main:app --host 127.0.0.1 --port 8091 --log-level info`. Test health with `/health`, create a run with `POST /v2/agent/runs`, plan with `/plan`, execute with `/execute`, and read trace with `/trace`. Use `/v2/chat/agent` for agentic tasks. Legacy `/chat` remains conversational.
