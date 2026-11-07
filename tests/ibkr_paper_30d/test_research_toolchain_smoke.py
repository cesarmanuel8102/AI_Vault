from __future__ import annotations

from ibkr_paper_30d.research_toolchain_smoke import run_research_toolchain_smoke
from test_research_toolchain_remediation import FakeSandbox


def test_toolchain_smoke_passes_every_capability_tool(tmp_path) -> None:
    sandbox = FakeSandbox()

    report = run_research_toolchain_smoke(tmp_path / "smoke-workspace", sandbox=sandbox)

    assert report["status"] == "PASS", report
    assert set(report["checks"]) == {
        "WORKSPACE_WRITE", "WORKSPACE_READ", "WORKSPACE_LIST", "WORKSPACE_DELETE",
        "WORKSPACE_ALIAS_ACTION", "RUN_RESEARCH_SCRIPT", "RUN_RESEARCH_SCRIPT_INPUTS",
        "QUANTCONNECT_STATUS",
    }
    assert all(item["status"] == "PASS" for item in report["checks"].values())
    assert sandbox.calls[-1]["arguments"][-1].startswith("/workspace/datasets/research_inputs/")


def test_toolchain_smoke_reports_failure_without_raising(tmp_path) -> None:
    class BrokenSandbox(FakeSandbox):
        def run(self, **kwargs):
            raise RuntimeError("sandbox down")

    report = run_research_toolchain_smoke(tmp_path / "smoke-workspace", sandbox=BrokenSandbox())

    assert report["status"] == "FAIL"
    assert report["checks"]["RUN_RESEARCH_SCRIPT"]["status"] == "FAIL"
    assert report["checks"]["WORKSPACE_WRITE"]["status"] == "PASS"
