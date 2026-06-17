# Cycle 6: runtime-8090-decision

- proposal: Keep 8090 untouched and use 8091 as active safe runtime while locked/unknown.
- mode: dry_run_readonly
- safety_gate_passed: true
- lesson: Avoids destabilizing existing service ownership.
- risk: Scope creep or implicit runtime mutation.
