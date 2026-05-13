# Archived orphan files

Files moved here on session 2026-05-01 because they were not referenced
by the active runtime (`tmp_agent/brain_v9`).

| File | Reason |
|------|--------|
| `brain_dev_mode.py` | Imported a non-existent class; broken at import time |
| `pad_console.py`, `pad_simple.py`, `pad_standalone.py` | Standalone CLI wrappers around old `brain_v3_chat_autenticado` (pre-PAD) |
| `godmode_helper.py` | Empty/legacy helper, no callers |
| `protocolo_autenticacion_desarrollador_v2.py` | Earlier draft superseded by `brain/protocolo_autenticacion_desarrollador.py` |
| `protocolo_autenticacion_desarrollador_min.py` | Stripped variant, also superseded |
| `brain_v3_chat_autenticado.py` | Predecessor to the v9 `/chat/introspectivo` flow |

Active PAD module:
`brain/protocolo_autenticacion_desarrollador.py` (Fernet-encrypted credentials,
TOTP MFA, witnesses whitelist, single-session lock).

Restore: `mv` back to original location if needed.
