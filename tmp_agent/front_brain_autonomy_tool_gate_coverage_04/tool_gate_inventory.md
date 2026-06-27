# FRONT-BRAIN-AUTONOMY-TOOL-GATE-COVERAGE-04

## Phase 1: Mutative Tool Inventory

**Starting HEAD**: 9259a56  
**Date**: 2026-06-27

---

## Summary

| Category | Count |
|----------|-------|
| Total mutative tools | 14 |
| Already gated via ExecutionGate.check() | 7 |
| In `_FS_WRITE_TOOLS` but ungated | 5 |
| Memory write tools (ungated) | 2 |
| Tools needing gate wiring | 5 |
| Tools needing direct sandbox | 2 |
| Tools OK (no change needed) | 7 |

---

## Tool-by-Tool Analysis

### Already Gated via ExecutionGate.check() ✅ (7 tools)

| Tool | File | Protection |
|------|------|------------|
| `run_command` | tools.py:958 | `gate.check("run_command", ...)` |
| `install_package` | tools.py:2368 | `gate.check("install_package", ...)` + `_bypass_gate` |
| `run_python_script` | tools.py:2397 | `gate.check("run_python_script", ...)` + `_bypass_gate` |
| `freeze_strategy` | tools.py:2474 | `gate.check("freeze_strategy", ...)` + `_bypass_gate` |
| `unfreeze_strategy` | tools.py:2533 | `gate.check("unfreeze_strategy", ...)` + `_bypass_gate` |
| `trigger_autonomy_action` | tools.py:2627 | `gate.check("trigger_autonomy_action", ...)` + `_bypass_gate` |
| `place_paper_order` | tools.py:2715 | `gate.check("place_paper_order", ...)` + `_bypass_gate` |
| `cancel_paper_order` | tools.py:2762 | `gate.check("cancel_paper_order", ...)` + `_bypass_gate` |

---

### In `_FS_WRITE_TOOLS` But Ungated ❌ (5 tools)

These tools are listed in `_FS_WRITE_TOOLS` in ExecutionGate (line 83-92) so they're supposed to be sandboxed, but they **don't call ExecutionGate.check()** — they only use `_safe_path()` + `_assert_write_allowed()`.

| Tool | File | Current Protection | Risk | Recommended Action |
|------|------|-------------------|------|-------------------|
| `edit_file` | tools.py:212 | `_safe_path + _assert_write_allowed` | high | **wire_gate** |
| `write_file` | tools.py:292 | `_safe_path + _assert_write_allowed` | high | **wire_gate** |
| `backup_file` | tools.py:300 | `_safe_path + _assert_write_allowed` | medium | **wire_gate** |
| `promote_staged_change` | tools.py:666 | delegated to `self_improvement.promote_staged_change` | high | **wire_gate** |
| `rollback_staged_change` | tools.py:673 | delegated to `self_improvement.rollback_change` | high | **wire_gate** |

**These 5 tools will bypass SelfDevSandbox entirely when called directly.**

---

### Memory Write Tools (Ungated) ❌ (2 tools)

| Tool | File | Current Protection | Risk | Recommended Action |
|------|------|-------------------|------|-------------------|
| `semantic_memory_ingest` | tools.py:323 | none | high | **direct_sandbox** |
| `semantic_memory_ingest_session` | tools.py:333 | none | high | **direct_sandbox** |

**These directly mutate semantic memory without any gate or sandbox evaluation.**

---

### Tools OK - No Change Needed ✅ (7 tools)

Already covered by ExecutionGate or classified as non-mutative.

---

## Bypass Coverage

| Bypass Mechanism | Tools Using It | Protected Path Coverage |
|------------------|----------------|------------------------|
| `_bypass_gate` kwarg | 7 tools (install_package, run_python_script, freeze_strategy, unfreeze_strategy, trigger_autonomy_action, place_paper_order, cancel_paper_order) | Gate itself enforces sandbox before bypass could apply (for tools that call gate) |
| GOD mode | ContextVar `_active_god_session` | Blocked by capability policy GOD denylist |
| `god_override` | capability_governor | Blocked by capability policy GOD denylist |
| R27 self-dev auto-approve | ExecutionGate lines 625-656 | Sandbox evaluates first |

---

## Recommended Actions

### 1. Wire Gate for 5 File Write Tools (Minimal Helper)

Add helper in `tools.py`:
```python
async def _runtime_gate_or_block(tool_name: str, args: dict, session_id: str = None) -> Optional[dict]:
    gate = get_gate()
    decision = gate.check(tool_name, args, session_id=session_id)
    if not decision["allowed"]:
        return decision
    return None
```

Call at start of `edit_file`, `write_file`, `backup_file`, `promote_staged_change`, `rollback_staged_change`.

### 2. Direct Sandbox for 2 Memory Tools

Add `evaluate_selfdev_action()` call at start of `semantic_memory_ingest` and `semantic_memory_ingest_session`.

---

## Files to Modify

1. `tmp_agent/brain_v9/agent/tools.py` — Add helper + wire 5 tools + direct sandbox 2 tools
2. (Optional) `tmp_agent/brain_v9/governance/execution_gate.py` — Small helper if needed

---

## Files NOT to Touch

- `memory/*` (forbidden)
- `trading/*` (forbidden)
- `session.py` (out of scope)