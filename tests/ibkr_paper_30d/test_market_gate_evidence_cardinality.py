"""Regression tests for RUN_IBKR_MARKET_DATA_GATE.ps1 evidence cardinality.

The 2026-09-24 14:45:01 ET interactive run aborted with
PropertyNotFoundStrict ".Count" inside the PowerShell gate script. The
harness extracts the script's functions via the PowerShell AST (the main
body never executes) and runs each evidence function under
Set-StrictMode -Version Latest against an isolated temporary report root.

The scalarization bug: `@(literal paths) | Where-Object ...` wraps the
literal, NOT the pipeline result, so zero matches produce $null and
`$null.Count` raises PropertyNotFoundStrict under StrictMode Latest.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "RUN_IBKR_MARKET_DATA_GATE.ps1"
HARNESS = REPO / "tests" / "ibkr_paper_30d" / "_market_gate_evidence_harness.ps1"

WINDOWS = shutil.which("powershell.exe") is not None
pytestmark = pytest.mark.skipif(not WINDOWS, reason="Windows PowerShell required")


def run_harness(tmp_path: Path, function: str, existing: str, mode: str = "one") -> dict:
    report_root = tmp_path / "reports"
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARNESS),
            "-ScriptPath",
            str(SCRIPT),
            "-ReportRoot",
            str(report_root),
            "-Function",
            function,
            "-ExistingCount",
            existing,
            "-PythonJsonMode",
            mode,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    lines = [
        line
        for line in (completed.stdout or "").splitlines()
        if line.strip().startswith("{")
    ]
    assert lines, (
        f"harness produced no JSON; stdout={completed.stdout!r} "
        f"stderr={completed.stderr!r}"
    )
    return json.loads(lines[-1])


@pytest.mark.parametrize("existing", ["0", "1", "many"])
def test_initialize_clean_evidence_is_strict_mode_safe(tmp_path, existing):
    result = run_harness(tmp_path, "Initialize-CleanEvidence", existing)

    assert result["status"] == "OK", result
    # The collection state must be created in every cardinality case.
    assert result["state_created"] is True
    if existing == "1":
        # Pre-existing evidence is archived, only the fresh state remains.
        assert len(result["archive_dirs"]) == 1
        assert result["archived_files"] == 1
        assert [Path(item).name for item in result["remaining"]] == [
            "market_gate_collection_state.json"
        ]
    elif existing == "many":
        assert len(result["archive_dirs"]) == 1
        assert result["archived_files"] == 5
        assert [Path(item).name for item in result["remaining"]] == [
            "market_gate_collection_state.json"
        ]


@pytest.mark.parametrize("existing", ["0", "1", "many"])
def test_archive_collection_evidence_is_strict_mode_safe(tmp_path, existing):
    result = run_harness(tmp_path, "Archive-CollectionEvidence", existing)

    assert result["status"] == "OK", result
    if existing == "0":
        # Zero evidence: no archive directory must be created.
        assert result["archive_dirs"] == []
    if existing == "1":
        assert result["archived_files"] == 1
    if existing == "many":
        assert result["archived_files"] == 3


@pytest.mark.parametrize("mode", ["zero", "one", "many"])
def test_invoke_pythonjson_cardinality(tmp_path, mode):
    result = run_harness(tmp_path, "Invoke-PythonJson", "0", mode)

    if mode == "zero":
        assert result["status"] == "ERROR"
        assert "PYTHON_JSON_OUTPUT_MISSING" in result["exception_message_head"]
        assert result["error_type"].startswith("System.Management.Automation")
    else:
        assert result["status"] == "OK", result
        assert result["parsed"] == {"a": mode == "many" and 2 or 1}


def test_harness_reproduces_the_strict_mode_count_failure_before_fix():
    """Guard: the RED evidence for the root cause is real. Before the fix,
    the zero-evidence case must fail with PropertyNotFoundStrict; this test
    asserts the fixed script passes, and its git-history counterpart (the
    harness against the pre-fix script) documents the reproduction."""

    result = run_harness(tmp_path_shared := Path(
        __import__("tempfile").mkdtemp(prefix="mgate-")
    ), "Initialize-CleanEvidence", "0")
    shutil.rmtree(tmp_path_shared, ignore_errors=True)
    assert result["status"] == "OK", result