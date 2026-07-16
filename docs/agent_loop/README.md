# Kimi–Codex GitHub Agent Loop

GitHub is the source of truth. Kimi writes through OpenCode in disposable local checkouts; deterministic GitHub Actions and Codex read-only supervision gate every HEAD. Human reauditing is required before merge.

Worker contract: `scripts/agent_loop/local_worker/worker_contract.json`.
Worker source: `scripts/agent_loop/local_worker/agent_worker.py`.

Hardening 02 adds Windows `.cmd` resolution, dynamic OpenCode flag detection, generation workspaces, a single-instance lock, bounded retries, mutually exclusive phase labels, preflight evidence, retention cleanup and final same-HEAD local reports. Auto-merge and synchronization with `C:\AI_VAULT_CANONICAL` remain prohibited.

