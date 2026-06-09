"""Smoke test for FRONT-INGESTION-REGISTRY-01.

Validates:
1. ingestion_registry module loads and is pure Python (no network, no file writes).
2. Default registry builds with at least 6 records.
3. All source_id values are unique.
4. Unknown source_type normalizes safely.
5. Unknown risk_level becomes blocked.
6. Blocked source is not dry-run allowed.
7. High risk source is not auto-ingest allowed.
8. Credential-sensitive source is not auto-ingest allowed.
9. Unknown content_policy requires operator review.
10. can_write_semantic_memory is false for all default records.
11. can_promote_faiss is false for all default records.
12. local_file default is dry_run_only.
13. api_reference default is blocked.
14. validate_source_record returns ok:false for missing source_id.
15. validate_source_record returns ok:false for invalid source_type.
16. classify_source_record includes residual_risk.
17. summarize_registry returns counts by risk/mode/type.
18. Module contains no requests/httpx/aiohttp imports.
19. Module contains no open(..., "w") or write_text.
20-27. Staging hygiene checks.
28. ROADMAP_STATUS.json remains valid.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path so brain/* imports resolve
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.ingestion_registry as ir


def test_module_imports_cleanly():
    assert callable(ir.normalize_source_id)
    assert callable(ir.build_source_record)
    assert callable(ir.validate_source_record)
    assert callable(ir.classify_source_record)
    assert callable(ir.build_default_registry)
    assert callable(ir.summarize_registry)


def test_default_registry_builds():
    registry = ir.build_default_registry()
    assert len(registry) >= 6


def test_all_source_ids_unique():
    registry = ir.build_default_registry()
    ids = [r["source_id"] for r in registry]
    assert len(ids) == len(set(ids)), f"Duplicate source_ids: {ids}"


def test_unknown_source_type_normalizes_safely():
    assert ir.normalize_source_type("weird_unknown") == "unknown"
    assert ir.normalize_source_type("LOCAL_FILE") == "local_file"


def test_unknown_risk_level_becomes_blocked():
    assert ir.normalize_risk_level("extreme") == "blocked"
    assert ir.normalize_risk_level("LOW") == "low"


def test_blocked_source_not_dry_run_allowed():
    blocked = ir.build_source_record(
        source_id="blocked_test",
        source_type="api_reference",
        uri="ref://blocked",
        risk_level="blocked",
        allowed_mode="blocked",
        content_policy="credential_sensitive",
    )
    assert ir.is_source_allowed_for_dry_run(blocked) is False


def test_high_risk_not_auto_ingest():
    high = ir.build_source_record(
        source_id="high_test",
        source_type="web_reference",
        uri="ref://web",
        risk_level="high",
        allowed_mode="registry_only",
        content_policy="public",
        can_auto_ingest=True,
    )
    assert ir.is_source_allowed_for_auto_ingest(high) is False


def test_credential_sensitive_not_auto_ingest():
    cred = ir.build_source_record(
        source_id="cred_test",
        source_type="api_reference",
        uri="ref://api",
        risk_level="low",
        allowed_mode="registry_only",
        content_policy="credential_sensitive",
        can_auto_ingest=True,
    )
    assert ir.is_source_allowed_for_auto_ingest(cred) is False


def test_unknown_content_policy_requires_operator_review():
    unknown = ir.build_source_record(
        source_id="unknown_test",
        source_type="manual_text",
        uri="inline://test",
        content_policy="unknown",
        requires_operator_approval=False,
    )
    v = ir.validate_source_record(unknown)
    assert v["ok"] is False
    assert "Unknown content_policy must have requires_operator_approval=True" in v["errors"]


def test_can_write_semantic_memory_false_all_defaults():
    registry = ir.build_default_registry()
    for r in registry:
        assert r["can_write_semantic_memory"] is False, f"{r['source_id']} has can_write_semantic_memory=True"


def test_can_promote_faiss_false_all_defaults():
    registry = ir.build_default_registry()
    for r in registry:
        assert r["can_promote_faiss"] is False, f"{r['source_id']} has can_promote_faiss=True"


def test_local_file_default_is_dry_run_only():
    registry = ir.build_default_registry()
    local_file = next(r for r in registry if r["source_id"] == "local_file_dry_run_only")
    assert local_file["allowed_mode"] == "dry_run_only"


def test_api_reference_default_is_blocked():
    registry = ir.build_default_registry()
    api_ref = next(r for r in registry if r["source_id"] == "api_reference_blocked_until_credentials_policy")
    assert api_ref["risk_level"] == "blocked"
    assert api_ref["allowed_mode"] == "blocked"


def test_validate_missing_source_id_fails():
    bad = ir.build_source_record(
        source_id="",
        source_type="manual_text",
        uri="inline://test",
    )
    v = ir.validate_source_record(bad)
    assert v["ok"] is False
    assert "Missing required field: source_id" in v["errors"]


def test_validate_invalid_source_type_fails():
    bad = ir.build_source_record(
        source_id="bad_type",
        source_type="totally_invalid_type",
        uri="inline://test",
    )
    v = ir.validate_source_record(bad)
    assert v["ok"] is False
    assert any("Invalid source_type" in e for e in v["errors"])


def test_classify_includes_residual_risk():
    r = ir.build_source_record(
        source_id="residual_test",
        source_type="manual_text",
        uri="inline://test",
        risk_level="low",
        content_policy="credential_sensitive",
    )
    c = ir.classify_source_record(r)
    assert "residual_risk" in c
    assert c["residual_risk"] == "high"


def test_summarize_returns_counts():
    registry = ir.build_default_registry()
    summary = ir.summarize_registry(registry)
    assert summary["total_records"] == len(registry)
    assert "by_risk_level" in summary
    assert "by_allowed_mode" in summary
    assert "by_source_type" in summary


def test_no_network_imports_in_module():
    src = Path("brain/ingestion_registry.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    bad = [i for i in imports if any(b in i for b in ("requests", "httpx", "aiohttp", "urllib"))]
    assert not bad, f"Forbidden network imports found: {bad}"


def test_no_file_writes_in_module():
    src = Path("brain/ingestion_registry.py").read_text(encoding="utf-8")
    assert "open(" not in src or 'mode="w"' not in src
    assert ".write_text(" not in src
    assert ".write_bytes(" not in src


def test_no_memory_semantic_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged


def test_no_faiss_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower()


def test_no_env_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_trading_or_b8_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_session_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_main_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "main.py" not in staged


def test_no_curated_runtime_lookup_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "curated_runtime_lookup.py" not in staged


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True, text=True, cwd="."
    )
    assert result.returncode == 0
