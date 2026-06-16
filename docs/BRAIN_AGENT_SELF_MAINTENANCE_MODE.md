# Brain Agent Self Maintenance Mode

Safe modes: `repo_maintenance_read_only`, `repo_maintenance_dry_run`, and `repo_maintenance_approval_required`. Agent V2 may inspect repo state, search code, read safe docs/code, run allowlisted smoke tests, propose patch dry-runs, and write run-local reports. It cannot apply patches, commit, push, mutate semantic/FAISS memory, touch trading, or place orders without future explicit approval gates.
