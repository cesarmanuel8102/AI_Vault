# Chat/Dashboard Diagnosis

- 8090: free/no listener during passive check.
- 8091: Brain healthy.
- 3000: free/no listener during passive check.
- 8092: free/no listener during passive check.
- /v1/chat/completions provider_probe route works on 8091.
- decision: create separate safe dashboard on 8092.
- reason: avoids touching 8090 and avoids modifying 8091 runtime for dashboard UI.

## Relevant Repo References

tools\verify_kimi_k2_6_provider_config.ps1:36:    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8091/v1/models" -TimeoutSec 8
tools\verify_kimi_k2_6_provider_config.ps1:47:        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 45
tools\setup_kimi_k2_6_provider_user_env.ps1:67:            restart_required = "Open a new terminal and restart Brain 8091"
tools\setup_kimi_k2_6_provider_user_env.ps1:80:            restart_required = "Open a new terminal and restart Brain 8091"
tests\tools\codex_brain_eval_harness.py:28:        base_url.rstrip("/") + "/chat/completions",
tests\tools\codex_brain_eval_harness.py:84:    parser.add_argument("--base-url", default="http://127.0.0.1:8091/v1")
docs\SEMANTIC_COHERENCE_VALIDATION_LAYER.md:263:# En chat() method, después de seleccionar route:
docs\SEMANTIC_COHERENCE_VALIDATION_LAYER.md:267:coherence_report = self.chat_metrics.validate_semantic_coherence(
docs\SEMANTIC_COHERENCE_VALIDATION_LAYER.md:283:final_report = self.chat_metrics.validate_semantic_coherence(
docs\SEMANTIC_COHERENCE_VALIDATION_LAYER.md:291:self.chat_metrics.record_coherence_validation(
docs\RUNTIME_RECOVERY_RUNBOOK.md:5:Recover observability (dashboard/chat/runtime) before any real execution. This
docs\RUNTIME_RECOVERY_RUNBOOK.md:14:| Brain V9 Server | 8090 | DOWN |
docs\RUNTIME_RECOVERY_RUNBOOK.md:15:| Open WebUI / Dashboard | 3000 | DOWN |
docs\RUNTIME_RECOVERY_RUNBOOK.md:28:curl -sS http://127.0.0.1:8090/health       # Brain V9 DOWN expected
docs\RUNTIME_RECOVERY_RUNBOOK.md:29:curl -sS http://127.0.0.1:3000              # Open WebUI DOWN expected
docs\RUNTIME_RECOVERY_RUNBOOK.md:32:### Step 2 — Start Brain V9 Server (port 8090)
docs\RUNTIME_RECOVERY_RUNBOOK.md:49:curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/health     # expect 200
docs\RUNTIME_RECOVERY_RUNBOOK.md:50:curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/dashboard  # expect 200
docs\RUNTIME_RECOVERY_RUNBOOK.md:51:curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/docs       # expect 200
docs\RUNTIME_RECOVERY_RUNBOOK.md:54:### Step 3 — Start Open WebUI / Dashboard (port 3000)
docs\RUNTIME_RECOVERY_RUNBOOK.md:60:3. Start Open WebUI container:
docs\RUNTIME_RECOVERY_RUNBOOK.md:87:1. dashboard/chat reachable
docs\RUNTIME_RECOVERY_RUNBOOK.md:100:- **App**: `brain_v9.main:app` (FastAPI)
docs\RUNTIME_RECOVERY_RUNBOOK.md:102:- **Port**: `8090`
docs\RUNTIME_RECOVERY_RUNBOOK.md:104:- **Dashboard**: `GET /dashboard`, `GET /dashboard-v2`
docs\RUNTIME_RECOVERY_RUNBOOK.md:105:- **Chat**: `POST /chat`, `POST /chat/introspectivo`
docs\RUNTIME_RECOVERY_RUNBOOK.md:115:2. Brain V9 server (port 8090)
docs\RUNTIME_RECOVERY_RUNBOOK.md:116:3. Open WebUI (port 3000, requires Docker)
docs\RUNTIME_RECOVERY_RUNBOOK.md:122:- Existing runbook: `docs/runtime_dashboard_chat_runbook.md`
docs\RUNTIME_ENTRYPOINTS.md:15:- **Puerto**: 8090
docs\RUNTIME_ENTRYPOINTS.md:16:- **Health Check**: `GET http://127.0.0.1:8090/health`
docs\RUNTIME_ENTRYPOINTS.md:17:- **Chat Endpoint**: `POST http://127.0.0.1:8090/chat`
docs\RUNTIME_ENTRYPOINTS.md:23:- **Estado**: NO asumir que es runtime activo de 8090
docs\RUNTIME_ENTRYPOINTS.md:28:# Antes de tocar chat/runtime, ejecutar grep
docs\RUNTIME_ENTRYPOINTS.md:29:grep -r "8090" tmp_agent/brain_v9/start_full_server.py
docs\RUNTIME_ENTRYPOINTS.md:50:- **Integración**: Integrado al chat para respuestas grounded
docs\RUNTIME_ENTRYPOINTS.md:75:netstat -ano | findstr "8090"
docs\RUNTIME_ENTRYPOINTS.md:78:curl -s http://127.0.0.1:8090/health
docs\runtime_dashboard_chat_runbook.md:9:Dashboard and chat reported as "not alive" by operator.
docs\runtime_dashboard_chat_runbook.md:21:- **App**: `brain_v9.main:app` (FastAPI)
docs\runtime_dashboard_chat_runbook.md:23:- **Port**: `8090`
docs\runtime_dashboard_chat_runbook.md:30:- **Files**: `tmp_agent/brain_v9/ui/dashboard.html`, `index.html`
docs\runtime_dashboard_chat_runbook.md:31:- **Endpoint**: `GET /dashboard` and `GET /dashboard-v2`
docs\runtime_dashboard_chat_runbook.md:32:- **Static files**: served at `/ui` via FastAPI StaticFiles
docs\runtime_dashboard_chat_runbook.md:35:- **Endpoint**: `POST /chat`
docs\runtime_dashboard_chat_runbook.md:36:- **Introspective endpoint**: `POST /chat/introspectivo`
docs\runtime_dashboard_chat_runbook.md:51:start "BrainV9" /MIN python -m uvicorn main:app --host 127.0.0.1 --port 8090
docs\runtime_dashboard_chat_runbook.md:56:powershell -ExecutionPolicy Bypass -File scripts\runtime\start_dashboard_and_chat.ps1
docs\runtime_dashboard_chat_runbook.md:69:curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/health     # expected: 200
docs\runtime_dashboard_chat_runbook.md:70:curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/dashboard  # expected: 200
docs\runtime_dashboard_chat_runbook.md:71:curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/docs       # expected: 200
docs\runtime_dashboard_chat_runbook.md:75:- `scripts/runtime/start_dashboard_and_chat.ps1` — NEW
docs\runtime_dashboard_chat_runbook.md:96:1. Start server with `scripts/runtime/start_dashboard_and_chat.ps1`
docs\runtime_dashboard_chat_runbook.md:97:2. Verify dashboard at `http://127.0.0.1:8090/dashboard`
docs\runtime_dashboard_chat_runbook.md:98:3. Verify chat at `POST http://127.0.0.1:8090/chat`
docs\runtime_dashboard_chat_runbook.md:103:(runtime recovery complete; dashboard/chat now diagnosable and bootable)
docs\REAL_EXECUTION_POLICY.md:35:| dashboard_ok | true |
docs\REAL_EXECUTION_POLICY.md:66:- Visible in dashboard/chat
docs\P2E_SEMANTIC_MEMORY_FINAL_PRE_EXECUTION_GATE.md:17:7. **Does NOT run any runtime** - Pure static evaluation
docs\P2E_SEMANTIC_MEMORY_EXTRA_FILE_DEPENDENCY_MAPPING.md:5:This document describes the **Semantic Memory Extra File Dependency Mapper** (P2-E Commit 4D-DependencyMapping), which performs static read-only dependency mapping of references to extra files detected in the memory/semantic directory.
docs\P2E_SEMANTIC_MEMORY_EXTRA_FILE_DEPENDENCY_MAPPING.md:59:This mapper uses ONLY static text scanning:
docs\P2E_SEMANTIC_MEMORY_EXTRA_FILE_DEPENDENCY_MAPPING.md:160:- Tokens: `import faiss`, `faiss.`, `load_index`, `uvicorn`, `FastAPI`
docs\P2E_SEMANTIC_MEMORY_EXTRA_FILE_DEPENDENCY_MAPPING.md:191:# Run static analysis
docs\P2E_SEMANTIC_MEMORY_EXTRA_FILE_DEPENDENCY_MAPPING.md:379:- [x] Read-only static analysis
docs\P2E_OBSERVABILITY.md:20:- Sea extensible para futuras integraciones (dashboards, alertas)
docs\P2E_OBSERVABILITY.md:192:3. Crear dashboard de métricas
docs\P2E_GOVERNED_CURATED_MEMORY_PROMOTION.md:118:| R12 | Tests pasan pero runtime no usa | Medio | Smoke test local sin dependencia de servidor 8090 |
docs\P2E_GOVERNANCE_CONTRACT.md:61:- No requiere servidor 8090
docs\P2E_DRY_RUN_PIPELINE_SMOKE.md:164:5. Crear dashboard de métricas
docs\P2E_DRY_RUN_FLOW.md:374:5. Crear dashboard de métricas
docs\P2D_CURATION_VALIDATION_ADAPTER_USAGE.md:57:❌ **NO conecta runtime/chat**: Sin dependencias de `brain_v9.core.session` ni `main.py`
docs\P2D_CURATION_VALIDATION_ADAPTER_USAGE.md:144:Ejemplo completo de uso del adapter sin runtime/chat.
tests\smoke\smoke_self_improvement_first_five_utility_evaluation_dry_run.py:205:def test_no_runtime_chat_integration():
tests\smoke\smoke_self_improvement_first_five_utility_evaluation_dry_run.py:208:    assert result["runtime_chat_integration"] is False
docs\OPERATOR_ACCESS_RUNBOOK.md:58:Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -Headers $headers -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
docs\OPERATOR_ACCESS_RUNBOOK.md:65:Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/latest?room_id=test&run_id=test&limit=20" -Method GET
docs\OPERATOR_ACCESS_RUNBOOK.md:71:Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
docs\OPERATOR_ACCESS_RUNBOOK.md:78:Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -Headers $headers -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
tests\smoke\smoke_self_improvement_first_five_real_patch_plan_review_dry_run.py:511:def test_no_runtime_chat_integration(monkeypatch, tmp_path):
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:1:# Open WebUI Brain Provider Runbook
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:4:- Base URL: `http://host.docker.internal:8091/v1`
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:6:- API key: use a dummy/local placeholder if Open WebUI requires one.
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:10:Invoke-WebRequest http://127.0.0.1:8091/v1/models -UseBasicParsing
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:13:## Validate From Open WebUI Container
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:15:curl http://host.docker.internal:8091/v1/models
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:20:curl -s http://host.docker.internal:8091/v1/chat/completions \
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:26:- Response object should be `chat.completion`.
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:32:Remove or disable the Open WebUI provider entry and return to the previous provider. Do not delete Brain runtime files or modify memory/semantic artifacts.
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:34:## 8090 Note
docs\OPENWEBUI_BRAIN_PROVIDER_RUNBOOK.md:35:Port `8090` remains pending until its owner can be classified safely. Do not kill unknown 8090 processes. Use `8091` until switchover is explicitly safe.
tests\smoke\smoke_self_improvement_first_five_real_patch_plan_dry_run.py:515:def test_no_runtime_chat_integration(monkeypatch, tmp_path):
docs\MIGRATION_RISK_REGISTER.md:36:3. **Smoke Tests**: `ops/smoke_brain_v9_8090.ps1` - Valida runtime real
docs\MIGRATION_RISK_REGISTER.md:47:| R5 | Usar ProjectStateProvider.get_project_status() en chat | AI | 2026-05-24 |
tests\smoke\smoke_self_improvement_first_five_real_patch_materialization_plan_dry_run.py:762:    def test_no_runtime_chat_integration(self, tmp_path, module):
tests\smoke\smoke_self_improvement_first_five_real_patch_materialization_plan_dry_run.py:765:        assert result.get("runtime_chat_integration") is None or result.get("runtime_chat_integration") is False
tests\smoke\smoke_self_improvement_first_five_real_patch_implementation_plan_review_dry_run.py:482:def test_no_runtime_chat_integration(module, tmp_path):
tests\smoke\smoke_self_improvement_first_five_real_patch_implementation_plan_dry_run.py:503:def test_no_runtime_chat_integration(module, tmp_path):
tests\smoke\smoke_self_improvement_first_five_real_patch_implementation_plan_dry_run.py:506:    assert "runtime" not in report.lower() or "chat" not in report.lower()
docs\MIGRATION_CONTROL_LEDGER.md:9:- **Puerto runtime**: 8090
docs\MIGRATION_CONTROL_LEDGER.md:21:- No trading real desde chat sin approval.
docs\MIGRATION_CONTROL_LEDGER.md:151:  - Runtime: Brain V9 activo en 8090, /health healthy, /brain/chat-product/status responde
docs\MIGRATION_CONTROL_LEDGER.md:213:  - db21ae89 — Enable governed real tools permission gate in chat (TOOL-01A/B)
docs\MIGRATION_CONTROL_LEDGER.md:215:  - 75811d31 — Fix stale dashboard routes with read-only aliases (DASH-02)
docs\MIGRATION_CONTROL_LEDGER.md:220:  - DASH-02 stale dashboard routes (/brain/utility/status, /brain/learning/proposals): ACCEPTED
docs\MIGRATION_CONTROL_LEDGER.md:329:  - B3 fake grounded dashboard/runtime, or N2 auto-approval API bypass depending on priority
docs\MIGRATION_CONTROL_LEDGER.md:336:  - c07cd180 — Fix B3 fake grounded dashboard/runtime: add HTTP health verification
docs\MIGRATION_CONTROL_LEDGER.md:339:  - tests/unit/test_b3_fake_grounded_dashboard_runtime.py
docs\MIGRATION_CONTROL_LEDGER.md:344:  - B3 fake grounded: `_dashboard_status_fastpath` returned hardcoded `"runtime: activo"` without verifying actual Brain V9 state
docs\MIGRATION_CONTROL_LEDGER.md:347:  - `_dashboard_status_fastpath` now returns `runtime_status`, `verified_by`, and `verification_method` fields
docs\MIGRATION_CONTROL_LEDGER.md:350:  - test_dashboard_fastpath_no_fake_active_without_verification: PASS
docs\MIGRATION_CONTROL_LEDGER.md:351:  - test_dashboard_fastpath_runtime_status_field_present: PASS
docs\MIGRATION_CONTROL_LEDGER.md:352:  - test_dashboard_fastpath_verified_by_field_present: PASS
docs\MIGRATION_CONTROL_LEDGER.md:391:  - 59fc02d0 — Bind chat turns to visual trace workspace
docs\MIGRATION_CONTROL_LEDGER.md:571:  - TOOL-01 and GAK operated as parallel authorities in BrainSession.chat()
docs\MIGRATION_CONTROL_LEDGER.md:610:  - legacy_runtime_snapshots: 150 (chat_brain_v3-v7, advisor_server variants, old brain/ modules)
docs\MIGRATION_CONTROL_LEDGER.md:829:- **RUNTIME_READONLY_LOOKUP_CHAT_01**: Implement explicit chat command
docs\MIGRATION_CONTROL_LEDGER.md:858:- **Commit**: 347eb1a5 — chat-ops: stabilize tool results, sequence control, and diff analysis
docs\MIGRATION_CONTROL_LEDGER.md:926:- EXTERNAL-CURATED-INGESTION-DRY-RUN-DEMO-01 after chat command or as explicit endpoint-only demo
docs\MIGRATION_CONTROL_LEDGER.md:935:- **Estado**: Runtime read-only lookup chat command implementado, validado, commiteado y sincronizado en GitHub.
docs\MIGRATION_CONTROL_LEDGER.md:938:- **Commit**: affc6614 — runtime: add read-only curated knowledge chat command
