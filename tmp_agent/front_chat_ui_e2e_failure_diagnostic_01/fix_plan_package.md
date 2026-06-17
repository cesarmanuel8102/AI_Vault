# Fix Plan Package

Generated: 2026-06-12T04:19:46.559951+00:00

- recommended_fix_front: FRONT-CHAT-UI-DOCKER-NETWORKING-FIX-01
- primary_failure: UI_NOT_REACHABLE

## Files likely to change
- Open WebUI/container/startup configuration if UI should run on 3000
- tmp_agent/brain_v9/main.py only if OpenAI-compatible adapter is chosen after UI is reachable
- tests/smoke/smoke_front_chat_ui_docker_networking_fix_01.py

## Success Criteria
- direct backend chat passes
- Open WebUI chat passes
- canonical retrieval evidence appears
- no raw CoT leakage
- response latency acceptable
- tests pass
