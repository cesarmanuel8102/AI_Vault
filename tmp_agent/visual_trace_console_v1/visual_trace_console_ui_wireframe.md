# Visual Trace Console v1 — UI Wireframe

## Layout General

```
+---------------------------------------------------------------+
| 🧠 Agent Visual Trace Console v1                              |
| Room: <room_id> | Run: <run_id> | Status: <status> | Mode: <mode> |
| Governance: <mode> | Last update: <ts>                        |
+---------------------------------------------------------------+
```

## Panel 1 — Header

- **room_id**: Identificador de la sesión/chat actual.
- **run_id**: Identificador del run actual (puede ser una propuesta o un request).
- **status**: running | completed | failed | blocked | waiting_approval.
- **mode**: edge_validated | learning_active | paper_mode | frozen.
- **governance**: strict | standard | audit.
- **last update**: timestamp último evento recibido.

## Panel 2 — Timeline (centro, scrollable)

Cada evento es una tarjeta horizontal:

```
+---------------------------------------------------------------+
| ⏳ | Plan created: Consolidate N5 evidence                   |
|    | Summary: Agent created a plan to wrap up N5 evidence.    |
|    | Step: planning | Status: running | 2026-05-28 10:00:00  |
+---------------------------------------------------------------+
| 🔧 | Tool requested: TOOL-01 filesystem write                 |
|    | Summary: Write report JSON to tmp_agent/n5/...            |
|    | Step: evidence_write | Status: blocked | 10:00:05        |
+---------------------------------------------------------------+
| ⚖  | Governance checked: blocked by policy                    |
|    | Policy: GAK-TOOL01-PATH                                   |
|    | Reason: Path is in allowlist but requires approval.     |
|    | Proposal: PROP-123 | Status: blocked | 10:00:06         |
+---------------------------------------------------------------+
| ✋  | Approval required                                         |
|    | Proposal PROP-123 to write tmp_agent/n5/report.json     |
|    | Requires operator review. | Status: pending | 10:00:07  |
+---------------------------------------------------------------+
| ✅ | Approval applied                                          |
|    | Operator approved PROP-123.                             |
|    | Status: approved | 10:00:15                           |
+---------------------------------------------------------------+
| 📄 | File changed                                              |
|    | tmp_agent/n5/report.json updated.                       |
|    | Commit hash: 641cddff | Status: success | 10:00:20    |
+---------------------------------------------------------------+
| 🧪 | Validation started                                        |
|    | py_compile on tmp_agent/n5/report.json                   |
|    | Status: running | 10:00:21                            |
+---------------------------------------------------------------+
| ✅ | Validation passed                                         |
|    | All checks passed.                                       |
|    | Status: success | 10:00:22                            |
+---------------------------------------------------------------+
| 📦 | Commit created                                            |
|    | Commit hash: 641cddff                                     |
|    | Files: 2 | Status: success | 10:00:25               |
+---------------------------------------------------------------+
| 🚀 | Push completed                                            |
|    | Branch: codex/own-capital-sustainable-return              |
|    | Status: success | 10:00:30                            |
+---------------------------------------------------------------+
| 🏁 | Run completed                                             |
|    | All steps completed successfully.                        |
|    | Status: success | 10:00:35                            |
+---------------------------------------------------------------+
```

## Panel 3 — Governance (lateral derecho)

```
Governance Decisions
+---------------------------------------------------+
| Allowed    | 5  | ✅ tool reads, validations        |
| Blocked    | 1  | ⚠ TOOL-01 write initially       |
| Requires   | 1  | ✋ PROP-123 approval             |
| Rejected   | 0  |                                   |
+---------------------------------------------------+
| Active Proposals                                  |
| PROP-123: approved | GAK-TOOL01-PATH                |
| PROP-124: pending  | GAK-SESSION-EDIT               |
+---------------------------------------------------+
```

## Panel 4 — Evidence (lateral derecho, debajo de governance)

```
Evidence References
+---------------------------------------------------+
| 📄 tmp_agent/n5/report.json                       |
| 📄 tmp_agent/n5/risk_matrix.json                  |
| 🔗 Commit: 641cddff                               |
| 🔗 Commit: 378b9134                               |
| 📊 Report: N5-FINDINGS-001                        |
+---------------------------------------------------+
```

## Panel 5 — Errors (lateral derecho, debajo de evidence)

```
Errors & Warnings
+---------------------------------------------------+
| ⚠ N5C-002: ambiguous duplicate module names       |
|   needs manual review.                            |
| 📊 Severity: medium | Count: 1                    |
+---------------------------------------------------+
```

## Panel 6 — Filters (barra superior, debajo de header)

```
[All] [Thinking] [Tool] [Evidence] [Governance] [Error] [Commit] [Approval]
```

## Event Type Icons

| Type | Icon |
|------|------|
| user_request_received | 👤 |
| plan_created | 📋 |
| step_started | ⏳ |
| tool_requested | 🔧 |
| tool_executed | ✅ |
| governance_checked | ⚖ |
| proposal_created | 📝 |
| approval_required | ✋ |
| approval_applied | ✅ |
| approval_rejected | ❌ |
| file_changed | 📄 |
| validation_started | 🧪 |
| validation_passed | ✅ |
| validation_failed | ❌ |
| commit_created | 📦 |
| push_completed | 🚀 |
| run_completed | 🏁 |
| run_failed | 💥 |

## Seguridad UI
- Tooltip en cada evento: "Operational trace only; private reasoning not shown."
- Context menu: "View sanitized summary" (no raw details).
- Governance panel: apply/reject buttons solo aparecen cuando decision = requires_approval.
- Evidence panel: muestra paths (redactados si protegidos) y report IDs, NO contenido completo.

## Responsive Notes
- Timeline es la zona principal; panels laterales colapsables en pantallas pequeñas.
- Event cards altura fija ~80px con scroll infinito.
- Colores por estado: pending = gris, running = azul, blocked = naranja, approved/éxito = verde, error/rejected = rojo.
