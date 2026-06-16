# Brain Agent Runtime Contract V2

Agent V2 is canonical for new agent operations. Statuses: created, planned, running, waiting_approval, paused, failed, completed, cancelled. Modes: read_only, dry_run, approval_required, write_allowed. Default mode is read_only. Traces are operational only and must not contain raw chain-of-thought. Memory retrieval is read-only; memory promotion is blocked inside Agent V2. Write tools require approval tokens and are blocked in read_only mode.
