# Lock Source Classification

- lock_source_detected: `unknown`
- confidence: `MEDIUM`
- safe_manual_action_needed: `true`
- reboot_recommended: `false`
- safe_mode_recommended: `true`

## Likely Sources
- Python process: PID `244420` is listening on port `8090`; command line is unavailable. This may be a Brain runtime/server process using the legacy path.
- Python/QC runner: PID `265004` command line references `tmp_agent\strategies\mean_reversion_eq\run_phase311_bull_put_guard_qc_revalidation_2026-06-12.py`; this was preexisting from the trading QC front and must not be killed by this diagnostic front.
- Ollama: PID `23388` listens on `11434`, but there is no direct evidence that it holds `C:\AI_VAULT`.
- VS Code/Cursor/Codex/Kimi or Windows file watchers remain possible.
- Defender/Search indexing remain possible but unproven.
- Exact handle owner is unknown because `handle.exe` / `handle64.exe` is not installed.

## Decision
Manual lock diagnostic is required before another retry. Do not run another blind rename attempt.
