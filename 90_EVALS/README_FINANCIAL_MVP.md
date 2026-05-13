# Financial MVP  Brain Lab

This folder is the **minimum economic control system** for the Brain Lab.

## Files
- 60_METRICS\capital_state.json
  - Source of truth for capital and risk limits.
- 60_METRICS\opportunity_scores.csv
  - Pipeline entry for opportunities (scoring + status).
- 60_METRICS\performance_history.csv
  - Weekly roll-up metrics over time.
- 50_LOGS\financial\financial.log
  - Append-only financial events.
- 50_LOGS\decisions\decisions.log
  - Append-only decisions and rationale.
- 90_EVALS\weekly_eval_template.md
  - Weekly evaluation format.

## Rules (MVP)
- Do not risk more than max_per_experiment_abs per hypothesis.
- Do not commit more than max_total_commit_abs simultaneously.
- Changes to risk rules only during weekly evaluation.

## Next step
After RAM upgrade, re-run your diagnostic script and then we proceed to implement:
- A tiny scoring function (Python) to compute score_total.
- A tiny capital allocator (Python) to approve/deny experiments within limits.