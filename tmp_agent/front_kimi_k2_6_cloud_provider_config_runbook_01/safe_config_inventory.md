# Safe Config Inventory

- secrets_exposed: `false`
- kimi_status: `KIMI_CONFIG_MISSING`

- KIMI_API_KEY: present=`false`, length=`0`, source_scope=`Unknown`, value_redacted=`true`
- MOONSHOT_API_KEY: present=`false`, length=`0`, source_scope=`Unknown`, value_redacted=`true`
- KIMI_BASE_URL: present=`false`, length=`0`, source_scope=`Unknown`, value_redacted=`true`
- MOONSHOT_BASE_URL: present=`false`, length=`0`, source_scope=`Unknown`, value_redacted=`true`

## Code References

- `tmp_agent/brain_v9/core/llm.py`: Kimi K2.6 provider slot and env-safe detection exist.
- `tmp_agent/brain_v9/api/openai_compat.py`: adapter delegates to router and preserves dry-run.
- `tmp_agent/brain_v9/core/session.py`: no secret handling required.
