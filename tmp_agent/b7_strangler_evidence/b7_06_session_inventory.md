# B7-STRANGLER-06-INVENTORY — Phase A: Session Inventory

**Source:** `tmp_agent/brain_v9/core/session.py` (5,743 lines, post-B7-05)
**BrainSession class:** L231–L5737 (5,507 lines), 173 methods (97 instance, 42 classmethod, 34 staticmethod)
**Top-level:** 1 class, 3 functions, 12 constants, 28 imports.

## Method-prefix groups (top 25 by total lines)

| Prefix | Count | Total lines | Pure | Pure lines | Notes |
|---|--:|--:|--:|--:|---|
| `_cmd_*` | 31 | 703 | 0 | 0 | slash-command handlers; high `self` coupling |
| `chat` | 1 | 644 | 0 | 0 | main entrypoint |
| `_route_*` | 2 | 564 | 0 | 0 | routing core (protected) |
| `_maybe_*` | 8 | 461 | 0 | 0 | fastpath gates |
| `_tool01_*` | 12 | 363 | 0 | 0 | Tool01 pipeline (protected) |
| **`_fmt_*`** | **17** | **295** | **17** | **295** | **all classmethod, all pure (self=0, cls=0)** |
| `_policy_*` | 1 | 187 | 0 | 0 | policy gate |
| `_should_*` | 3 | 150 | 2 | 72 | mixed |
| `_render_*` | 2 | 116 | 2 | 116 | both pure classmethods |
| `_is_*` | 32 | 111 | 30 | 65 | small predicates (mostly already-extracted lookalikes) |
| `_format_*` | 2 | 66 | 2 | 66 | dispatcher + action value |
| `_truncate_*` | 2 | 54 | 2 | 54 | budget helpers |
| `_build_*` | 2 | 50 | 2 | 50 | grounded excerpt builders |
| `_extract_*` | 2 | 43 | 2 | 43 | candidate path / symbol hint |

## Pure modular candidates summary

64 methods (`@staticmethod`/`@classmethod` with `self_uses_total==0` AND `cls_uses_total==0`), totalling 563 lines.
The dominant cluster is **`_fmt_*` = 17 methods / 295 lines (52% of all pure-modular surface)**.

## Raw evidence
- `_b7_06_inventory_raw.json` (initial AST scan)
- `_b7_06_inventory_extra.json` (extended scan: prefix groups, body deep dive, repo-wide caller search)
