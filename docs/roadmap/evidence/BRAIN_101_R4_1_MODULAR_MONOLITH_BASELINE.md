# R4.1 Modular-Monolith Baseline and Boundary Inventory

## Scope and Canonical Inputs

- `CANONICAL_BASE_SHA`: `f455904b98d9bc1ed690e7948f99d9200a13cce4`
- `FILE_LIST_SHA256`: `fbdbc1109d560eb568f49071c7e0bed9d938933e3d6c808f99656224c6b5f3e1`
- `INVENTORY_INPUT_SHA256`: `b6c94e2181627a3674c623831673ee2de1edd4abe7b39adb97810e94ee7db062`
- Measurement source: `git ls-tree -r --name-only HEAD -- tmp_agent/brain_v9`, Python import scans, file line counts, test-reference scans, and the most recent forty path-local commits.
- This is an architecture-only, read-only inventory. It does not start a server, broker, scheduler, provider, agent, trading component, or deployment.

The following LF-normalized input table is the exact material hashed as `INVENTORY_INPUT_SHA256`:

```text
CANONICAL_BASE_SHA=f455904b98d9bc1ed690e7948f99d9200a13cce4
FILE_LIST_SHA256=fbdbc1109d560eb568f49071c7e0bed9d938933e3d6c808f99656224c6b5f3e1
ENTRYPOINT|LOC|INTERNAL_IMPORTS|KNOWN_TEST_FILES|EFFECT_CLASS
main.py|2420|76|95|FastAPI assembly; server/process imports
core/session.py|3052|41|36|chat, memory, tool/provider orchestration
agent/tools.py|3519|18|0|tool execution boundary
agent/loop.py|2912|11|0|agent cycle orchestration
core/router_entrypoint.py|344|6|3|governed chat boundary
core/chat_entrypoint_service.py|469|11|0|chat request service
core/agent_kernel_v2/runtime.py|188|5|3|agent runtime adapter
CANDIDATE|VALUE_TO_BOUNDARY_CLARITY|TEST_READINESS|ROLLBACK_REVERSIBILITY|SHARED_STATE_CONTAINMENT|CHANGE_BLAST_RADIUS|SCORE
router response-governance helper extraction|5|5|5|5|1|29
chat input/output contracts extraction|3|4|5|5|2|23
session memory-state extraction|2|5|4|3|3|18
```

## Entry Point Inventory

| Entrypoint or boundary | LOC | Import lines | Test-reference files | Observed responsibility |
| --- | ---: | ---: | ---: | --- |
| `main.py` | 2420 | 76 | 95 | FastAPI assembly and legacy surface composition; imports server and process facilities. |
| `core/session.py` | 3052 | 41 | 36 | Chat, memory, tool, and provider orchestration. |
| `agent/tools.py` | 3519 | 18 | 0 | Tool execution boundary. |
| `agent/loop.py` | 2912 | 11 | 0 | Agent-cycle orchestration. |
| `core/router_entrypoint.py` | 344 | 6 | 3 | Governed chat-entry boundary. |
| `core/chat_entrypoint_service.py` | 469 | 11 | 0 | Chat request service boundary. |
| `core/agent_kernel_v2/runtime.py` | 188 | 5 | 3 | Agent V2 runtime adapter. |

## Module Ownership Map

`main.py` owns application composition. `core/session.py` owns the historical chat session orchestration. `core/router_entrypoint.py` owns the canonical chat boundary and delegates to `BrainSession` only after selecting a governed route. `core/agent_kernel_v2` owns the Agent V2 runtime adapter. `agent`, `autonomy`, `brain`, `governance`, `learning`, `memory`, `monitoring`, `operations`, `routes`, and `trading` retain separate ownership; `trading` is out of R4.1 scope.

## Dependency Boundary Map

`main.py` is a high-fan-in composition root and is not an extraction candidate. `session.py` imports numerous extracted helper modules and remains coupled to providers, memory, tools, and persisted state. `router_entrypoint.py` imports only configuration and intent detection at module load; response hygiene is a private helper region that dynamically invokes the existing session sanitizer. The router has no import edge to a new service, network boundary, or deployment component.

## Shared-State Inventory

`session.py` and the agent/autonomy modules manage session, memory, provider, or tool state and are excluded from this first extraction. `router_entrypoint.py` has `_ENTRYPOINT_SESSIONS` for session reuse, but its response-governance helper functions do not read or write that map. The candidate below has no durable state, no mutable global input, and no cross-boundary ownership cycle.

## Side-Effect Inventory

The router's normal path may call `BrainSession.chat`; the `provider_probe` path may call a provider probe. The response-governance helper itself only filters response data and invokes the existing in-process sanitizer. It performs no network call, file write, process launch, tool execution, memory write, FAISS write, scheduler activation, trading action, or deployment. R4.2 must preserve that separation and must not move the normal/provider execution paths.

## Coupling and Hotspots

The largest coupled modules are `agent/tools.py` (3519 LOC), `session.py` (3052 LOC), `agent/loop.py` (2912 LOC), and `main.py` (2420 LOC). They have larger blast radii and/or side-effect ownership. The router is a 344-line boundary with existing smoke coverage and a narrow, internally cohesive response-hygiene region. Historical commits show it was introduced and amended independently, supporting a reversible internal extraction.

## Extraction Candidates

Score formula: `2*value_to_boundary_clarity + test_readiness + rollback_reversibility + shared_state_containment + (5-change_blast_radius)`.

| Candidate | Boundary clarity | Test readiness | Rollback | Shared state | Blast radius | Score | Eligibility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Router response-governance helper extraction | 5 | 5 | 5 | 5 | 1 | 29 | Eligible |
| Chat input/output contracts extraction | 3 | 4 | 5 | 5 | 2 | 23 | Not selected; less immediate boundary value. |
| Session memory-state extraction | 2 | 5 | 4 | 3 | 3 | 18 | Not selected; closer to session state and larger integration risk. |

The selected candidate is unique at the maximum eligible score. It has no unresolved cross-boundary cycle, no public-interface migration (the existing `apply_governance` import remains a compatibility re-export), no financial or trading effect, an explicit contract test, and a one-commit rollback.

## R4.2 Recommendation

```json
{
  "roadmap_item_id": "R4.2",
  "candidate": "router response-governance helper extraction",
  "score": 29,
  "deployment_mode": "NO_DEPLOY",
  "network_boundary": false,
  "public_interface_migration": false,
  "allowed_paths": [
    "tmp_agent/brain_v9/core/router_entrypoint.py",
    "tmp_agent/brain_v9/core/router_response_governance.py",
    "tests/contract/test_r4_2_router_response_governance.py"
  ],
  "forbidden_paths": [
    ".env",
    "tmp_agent/brain_v9/trading/",
    "financial_autonomy/",
    "memory/",
    "scripts/"
  ],
  "test_commands": [
    "python -m pytest -q tests/contract/test_r4_2_router_response_governance.py",
    "python -m pytest -q tests/smoke/smoke_front_chat_router_preservation_entrypoint_01.py",
    "git diff --check"
  ],
  "rollback": "Revert the router helper import, compatibility re-export, new internal helper, and its contract test together; no state or external effect requires recovery."
}
```

## Rollback Strategy

R4.1 is documentation and a contract test only. Reverting its evidence and test restores the exact prior source tree. The recommended R4.2 change is constrained to an internal helper, the existing router compatibility surface, and one contract test; its rollback is a normal source revert and has no persistent-state, deployment, or external-effect recovery.

## Required Tests

R4.1 requires the roadmap contract test and `git diff --check`. R4.2 must add the stated focused contract test, run the existing router-preservation smoke test, and preserve the existing exported `apply_governance` behavior. No runtime installation or scheduled-task test is required because both R4.1 and R4.2 are `NO_DEPLOY`.

## Hard Limits

- `HUMAN_FINAL_AUTHORITY=true`
- `AUTO_MERGE=false`
- `CANONICAL_LOCAL_SYNC=false`
- `LIVE_TRADING=false`
- `REAL_MONEY=false`
- `PERSISTENT_AGENT_LOOP=DEFERRED_DISABLED`
- No microservice, RPC, queue, network boundary, public-interface migration, provider call, broker call, financial operation, server launch, deployment, scheduler activation, or canonical local sync is authorized by R4.1.
