# Rollback Plan

1. Revert functional commit only if provider routing regresses.
2. Restore previous CHAINS/MODELS block in `tmp_agent/brain_v9/core/llm.py`.
3. Restore previous nominal budget-skip behavior if capped attempts cause unacceptable latency.
4. Restart only classified Brain V9 runtime on 8091.
5. Re-run smoke tests and immutability verification.
