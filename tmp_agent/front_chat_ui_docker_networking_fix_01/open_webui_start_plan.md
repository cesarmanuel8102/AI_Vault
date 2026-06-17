# Open WebUI Start / Recreate Plan

Generated: 2026-06-12T04:30:36.381278+00:00

- decision: START_EXISTING_OPEN_WEBUI
- reason: Open WebUI candidate exists but is not running
- command: `docker run -d --name open-webui -p 3000:8080 -e OLLAMA_BASE_URL=http://host.docker.internal:11434 -v open-webui:/app/backend/data --restart unless-stopped ghcr.io/open-webui/open-webui:main`
