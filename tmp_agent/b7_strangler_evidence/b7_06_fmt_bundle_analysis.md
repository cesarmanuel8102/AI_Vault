# B7-STRANGLER-06-INVENTORY — Phase C: `_fmt_*` Bundle Deep Analysis

## Confirmations (8/8)

| # | Item | Status |
|--:|---|---|
| 1 | Exact 17 `_fmt_*` methods | ✅ Confirmed |
| 2 | All `cls_uses_total == 0` | ✅ Confirmed |
| 3 | All `self_uses_total == 0` | ✅ Confirmed |
| 4 | `_TOOL_FORMATTERS` is the dispatch model | ✅ Confirmed (L4780–4800, 21 lines) |
| 5 | `_format_tool_result` uses `getattr(cls, name)` | ✅ Confirmed (L4803–4847) |
| 6 | Decision: extract `_fmt_*` only vs include dispatcher | ✅ Extract `_fmt_*` only |
| 7 | Shim form decided | ✅ `@classmethod def _fmt_x(cls, out): return fmt_x(out)` |
| 8 | Shim form preserves `getattr(cls, name)` | ✅ Verified by descriptor semantics |

## Bundle inventory (17 methods, 295 lines)

| Method | Lines | Size |
|---|--:|--:|
| `_fmt_check_port` | 4447–4473 | 27 |
| `_fmt_check_http_service` | 4476–4486 | 11 |
| `_fmt_check_all_services` | 4489–4502 | 14 |
| `_fmt_check_service_status` | 4505–4517 | 13 |
| `_fmt_get_live_autonomy_status` | 4520–4537 | 18 |
| `_fmt_run_diagnostic` | 4540–4552 | 13 |
| `_fmt_get_system_info` | 4555–4568 | 14 |
| `_fmt_run_command` | 4571–4581 | 11 |
| `_fmt_read_file` | 4584–4591 | 8 |
| `_fmt_list_directory` | 4594–4608 | 15 |
| `_fmt_search_files` | 4611–4625 | 15 |
| `_fmt_list_processes` | 4628–4642 | 15 |
| `_fmt_grep_codebase` | 4646–4665 | 20 |
| `_fmt_list_recent_brain_changes` | 4668–4694 | 27 |
| `_fmt_get_chat_metrics` | 4697–4720 | 24 |
| `_fmt_semantic_memory_search` | 4723–4744 | 22 |
| `_fmt_get_technical_introspection` | 4747–4774 | 28 |

## Builtin call surface (only stdlib)

`isinstance` ×35, `len` ×25, `str` ×16, `sorted` ×2, `list` ×1, `sum` ×1. No external module dependencies.

## Dispatcher model

```python
# session.py L4780-4800
_TOOL_FORMATTERS = {
    "check_port":              "_fmt_check_port",
    "check_http_service":      "_fmt_check_http_service",
    "check_url":               "_fmt_check_http_service",  # alias
    "check_all_services":      "_fmt_check_all_services",
    ...
}

# session.py L4803-4847
@classmethod
def _format_tool_result(cls, tool_name, out):
    name = cls._TOOL_FORMATTERS.get(tool_name)
    fn = getattr(cls, name, None) if name else None
    return fn(out) if fn else default
```

**Critical invariant:** `getattr(cls, name)` must resolve to a callable bound such that `fn(out)` works. This requires the formatter to be a `@classmethod` (descriptor protocol returns a bound method with `cls` pre-applied; remaining arity = `(out,)`).

## Shim form decision

**Selected:** `@classmethod def _fmt_x(cls, out): return fmt_x(out)`

| Form | Viable? | Reason |
|---|---|---|
| `_fmt_x = classmethod(fmt_x)` | ❌ | `fmt_x(out)` has no `cls` param; classmethod descriptor would inject `cls`, breaking arity |
| `_fmt_x = classmethod(lambda cls, out: fmt_x(out))` | ⚠️ Works but hurts traceback | 17 lambdas — opaque debugging |
| **`@classmethod def _fmt_x(cls, out): return fmt_x(out)`** | ✅ | Preserves `getattr(cls, name)`, readable tracebacks, easy future cleanup |

## Net reduction estimate

- Bundle removed: **−295 lines**
- Shim added: **+~51 lines** (17 × 3-line shims)
- **Net: ≈ −244 lines** in `session.py`

## Compatibility tests required (Phase D)

1. For each of 18 `_TOOL_FORMATTERS` keys (17 unique + 1 alias `check_url`), invoke `BrainSession._format_tool_result(key, mock_payload)` and assert non-default rendering.
2. Assert `getattr(BrainSession, '_fmt_<name>')` is callable AND has classmethod descriptor binding.
3. For each of 17 names: assert `fmt_<name>(out) == BrainSession._fmt_<name>(out)` for representative `out`.
