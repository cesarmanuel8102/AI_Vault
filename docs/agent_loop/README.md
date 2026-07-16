# Kimi–Codex GitHub Agent Loop

GitHub is the source of truth for repository state and every candidate PR. Kimi writes through OpenCode in disposable local checkouts; deterministic GitHub Actions and Codex read-only supervision gate every HEAD. Human reauditing is required before merge.

Worker contract: `scripts/agent_loop/local_worker/worker_contract.json`.
Worker source: `scripts/agent_loop/local_worker/agent_worker.py`.

Hardening 02.1 adds Windows `.cmd` resolution, dynamic OpenCode flag detection, generation workspaces, a single-instance lock, bounded retries, mutually exclusive phase labels, preflight evidence, retention cleanup, final same-HEAD local reports, trusted profile path allowlists and a shell-denied Kimi execution boundary. Auto-merge and synchronization with `C:\AI_VAULT_CANONICAL` remain prohibited.

## Deliberate limitation

Version 1.5.1 is **pilot-only**. It accepts only `agent/pilot-*`, only the `pilot` test profile and only the two pilot report paths. It is not authorized or technically capable of executing Brain front 16C. A separately reviewed `GENERAL-FRONT-03` must introduce generic front profiles and workflows before any production code front is queued.
