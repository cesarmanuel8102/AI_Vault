# Cycle 2: empty-response-discipline

- proposal: Treat empty Kimi/Ollama responses as provider failure, never as success.
- mode: dry_run_readonly
- safety_gate_passed: true
- lesson: K2.5 diagnostic produced empty content, validating the guard.
- risk: Scope creep or implicit runtime mutation.
