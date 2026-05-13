# brain_openai_fastapi

Servidor FastAPI para "Brain OpenAI" (local). Estructura mínima:

- src/app/main.py: app + healthz
- src/app/config.py: settings (env)
- src/app/logging_setup.py: logger
- src/app/routers/agent_proxy.py: proxy/adapter placeholder
- run_dev.ps1: runner con uvicorn

## Run
pwsh -ExecutionPolicy Bypass -File .\run_dev.ps1