# Brain Lab — Phase 3 Contract (Mínimo) — 2026-02-24

## Endpoints (mínimos)

- GET /health
  - respuesta esperada: { ok: true, service: "brain_router" }

- POST /v1/agent/mission  (requiere body JSON)
  - headers: x-room-id: <room>
  - body:
    {
      "objective": "string",
      "constraints": ["string", ...]
    }
  - respuesta: { ok: true, ... }
  - persistencia: C:\AI_VAULT\state\<room>\mission.json

- POST /v1/agent/plan  (requiere body JSON, puede ser "{}")
  - headers: x-room-id: <room>
  - body: {}
  - respuesta: { ok: true, ... }
  - persistencia: C:\AI_VAULT\state\<room>\plan.json

- POST /v1/agent/run  (requiere body JSON, puede ser "{}")
  - headers: x-room-id: <room>
  - body: {}
  - respuesta: { ok: true, ... }
  - efecto: loop plan→execute→evaluate
  - persistencia:
    - C:\AI_VAULT\state\<room>\episode.json (event log)
    - C:\AI_VAULT\state\<room>\policy_events.ndjson
    - C:\AI_VAULT\state\<room>\policy_registry.json

- POST /v1/agent/step/execute
- POST /v1/agent/step/evaluate
- GET /v1/agent/episode/latest
- GET /v1/agent/episode/review/latest
- POST /v1/agent/policy
- POST /v1/agent/evaluate

## Archivos de estado por room (observado)

C:\AI_VAULT\state\<room>\:
- mission.json
- plan.json
- episode.json
- episode_current.json
- policy_events.ndjson
- policy_registry.json
- memory_facts.jsonl (+ backups)
- memory_rank.json
- episodes\ (carpeta)

## Plan (estructura observada)

plan.json:
- room_id: string
- mission_objective: string
- created_at / updated_at: int (epoch)
- cursor: int
- steps: array
  - id: "s1" | "s2" | ...
  - title: string
  - action: "TOOL" | ...
  - tool: "write_file" | "list_dir" | ...
  - args: object
  - success_criteria: string
  - status: "pending" | "done" | "failed"
  - result: object (tool output)
  - started_at / ended_at: int (epoch)
- policy_gate:
  - score: number
  - violations: []
  - verdict: "continue" | "replan" | "halt"
  - notes: string

## Smoke test (anti-regresión)

Archivo:
- C:\AI_VAULT\workspace\brainlab\tests\phase3_smoke.ps1

Requisitos:
- server arriba en 127.0.0.1:8000
- ejecuta mission→plan→run
- valida good.txt creado
- valida run_evaluated existe en episode/latest
