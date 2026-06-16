# Tool Gateway Inventory

```json
{
  "capabilities": [
    {
      "allowed_modes": [
        "read_only",
        "dry_run",
        "approval_required",
        "write_allowed"
      ],
      "description": "Read git status and HEAD",
      "name": "repo_status_read",
      "read_only": true,
      "requires_approval": false,
      "risk_level": "low"
    },
    {
      "allowed_modes": [
        "read_only",
        "dry_run"
      ],
      "description": "Read a safe text file",
      "name": "file_read",
      "read_only": true,
      "requires_approval": false,
      "risk_level": "low"
    },
    {
      "allowed_modes": [
        "read_only",
        "dry_run"
      ],
      "description": "Search repository text with rg",
      "name": "grep_search",
      "read_only": true,
      "requires_approval": false,
      "risk_level": "low"
    },
    {
      "allowed_modes": [
        "read_only",
        "dry_run"
      ],
      "description": "Probe a local HTTP route",
      "name": "route_probe",
      "read_only": true,
      "requires_approval": false,
      "risk_level": "low"
    },
    {
      "allowed_modes": [
        "read_only",
        "dry_run"
      ],
      "description": "Read-only semantic retrieval",
      "name": "semantic_retrieve",
      "read_only": true,
      "requires_approval": false,
      "risk_level": "low"
    },
    {
      "allowed_modes": [
        "read_only",
        "dry_run"
      ],
      "description": "Run a focused read-only smoke test",
      "name": "smoke_test_readonly",
      "read_only": true,
      "requires_approval": false,
      "risk_level": "medium"
    },
    {
      "allowed_modes": [
        "dry_run",
        "approval_required",
        "write_allowed"
      ],
      "description": "Write run-local artifacts only",
      "name": "report_writer",
      "read_only": false,
      "requires_approval": false,
      "risk_level": "medium"
    },
    {
      "allowed_modes": [
        "dry_run",
        "approval_required"
      ],
      "description": "Preview a file patch",
      "name": "file_patch_dry_run",
      "read_only": false,
      "requires_approval": false,
      "risk_level": "medium"
    },
    {
      "allowed_modes": [
        "approval_required",
        "write_allowed"
      ],
      "description": "Apply a patch only with approval",
      "name": "file_patch_apply_approval_required",
      "read_only": false,
      "requires_approval": true,
      "risk_level": "high"
    },
    {
      "allowed_modes": [
        "approval_required",
        "write_allowed"
      ],
      "description": "Commit only with approval",
      "name": "git_commit_approval_required",
      "read_only": false,
      "requires_approval": true,
      "risk_level": "high"
    }
  ]
}
```
