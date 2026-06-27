# FRONT-BRAIN-AUTONOMY-RUNTIME-INTEGRATION-03

## Phase 1: Runtime Integration Inventory

**Starting HEAD**: 4f17d9c  
**Date**: 2026-06-27

---

### ExecutionGate.check() — Primary Integration Point

**Location**: `tmp_agent/brain_v9/governance/execution_gate.py`, lines 507-677

The `ExecutionGate.check()` method is the single gate for all tool invocations. It already handles:
- Risk classification (P0-P3)
- PLAN/BUILD mode enforcement
- GOD mode bypass (with P3 block)
- Self-dev R27 auto-approve
- Protected path denylist (governance/security files)
- Audit logging

**This is the safest minimal integration point.**

---

### File Write Tools (Currently UNCHECKED by ExecutionGate)

| Tool | Location | Current Check |
|------|----------|---------------|
| `edit_file` | tools.py:212 | `_safe_path()` + `_assert_write_allowed()` |
| `write_file` | tools.py:292 | `_safe_path()` + `_assert_write_allowed()` |
| `backup_file` | tools.py:300 | `_safe_path()` + `_assert_write_allowed()` |
| `promote_staged_change` | tools.py:666 | Delegated to self_improvement module |
| `rollback_staged_change` | tools.py:673 | Delegated to self_improvement module |

**Gap**: These tools don't call `ExecutionGate.check()` — they bypass the entire gate system.

---

### Gate-Checked Tools (Already Protected)

| Tool | Gate Call Location |
|------|-------------------|
| `run_command` | tools.py:970 |
| `kill_process` | tools.py:2355 |
| `install_package` | tools.py:2384 |
| `run_python_script` | tools.py:2420 |
| `freeze_strategy` | tools.py:2485 |
| `unfreeze_strategy` | tools.py:2544 |
| `trigger_autonomy_action` | tools.py:2637 |
| `place_paper_order` | tools.py:2724 |
| `cancel_paper_order` | tools.py:2771 |
| `auto_promote_strategies` | tools.py:2833 |
| `scan_ibkr_signals` | tools.py:2861 |
| `iterate_strategy` | tools.py:2903 |

---

### Bypass Mechanisms Identified

| Bypass | Location | Risk |
|--------|----------|------|
| `_bypass_gate` kwarg | ~10 tools (lines 2351, 2380, 2416, 2480, 2539, 2632, 2720, 2767, 2829, 2857, 2899) | Skips `ExecutionGate.check()` entirely |
| R27 self-dev auto-approve | execution_gate.py:625-656 | Auto-approves P2 self-dev tools if settings allow |
| GOD mode | execution_gate.py:544-585, tools.py:113-122 | ContextVar bypasses `_safe_path()` and `_assert_write_allowed()` |
| `god_override` | capability_governor.py | Passes `_bypass_gate=True` to install_package |
| `_god_active()` | tools.py:113-122 | Returns True if `_active_god_session` ContextVar has session |

---

### Protected Path Checks (Already Exist)

| Check | Location |
|-------|----------|
| `_is_protected_selfdev_path()` | execution_gate.py:105-121 |
| `protected_paths.is_protected_path()` | protected_paths.py (fallback) |
| `_assert_write_allowed()` | tools.py:146-155 |
| `_is_tool01_protected_path()` | tools.py:100-109 |

---

### Selected Integration Approach

**Minimal**: Add `SelfDevSandbox` evaluation inside `ExecutionGate.check()` for `_FS_WRITE_TOOLS` **before** GOD mode and R27 bypass checks.

**Why ExecutionGate.check()?**
- Single choke point for all tool invocations
- Already handles mode, risk, GOD, self-dev, protected paths
- Returns structured decision with `allowed`, `risk`, `reason`, `action`, `pending_id`
- Audit logging already implemented

**Changes to execution_gate.py**:
1. Import `SelfDevSandbox` / `evaluate_selfdev_action`
2. In `check()`, after risk classification but **before** GOD mode and R27 bypass
3. For tools in `_FS_WRITE_TOOLS`, call `evaluate_selfdev_action()` with `is_god_mode` flag
4. If denied: return structured deny with `write_performed=false` and `audit_event`

**Files to Modify**: Only `tmp_agent/brain_v9/governance/execution_gate.py`

**Files NOT to Touch**:
- `tmp_agent/brain_v9/agent/tools.py` (too many changes)
- `tmp_agent/brain_v9/brain/self_improvement.py` (internal logic)
- `memory/*` (forbidden)
- `trading/*` (forbidden)