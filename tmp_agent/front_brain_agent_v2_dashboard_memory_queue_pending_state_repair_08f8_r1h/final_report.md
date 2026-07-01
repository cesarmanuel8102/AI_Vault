# FRONT_BRAIN_AGENT_V2_DASHBOARD_MEMORY_QUEUE_PENDING_STATE_REPAIR_08F8_R1H

Status: IMPLEMENTED

Root cause refined: the dashboard count 57 is a raw file count from memory/promotion_queue/*.json, but active pending review is not the same metric.

Deterministic counts:
- dashboard raw promotion_queue_count: 57
- active eview_required=true: 0
- eview_required=false: 57
- esolved_utc present: 57
- terminal statuses:
  - approved_for_canonical_promotion: 6
  - promoted_to_canonical: 6
  - archived_duplicate: 12
  - archived_superseded: 33

Validation:
- py_compile: PASS
- smoke: 10 passed
- no memory/semantic writes
- no FAISS writes
- no trading touched

Files changed:
- tmp_agent/brain_v9/core/agent_kernel_v2/evidence_tools.py
- tests/smoke/test_brain_agent_v2_agentic_benchmark_gap_repair_08f8_r1d.py
