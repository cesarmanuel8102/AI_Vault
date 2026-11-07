"""Non-destructive smoke check of the model research capability tools.

Runs against a throw-away workspace (never the live model workspace) so the
model's artifacts and registry are untouched. No broker toolbox is used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .autonomous_research import ResearchRequest, ResearchResult, ResearchTool
from .autonomy_toolbox import AutonomyToolbox, QuantConnectMediator
from .autonomy_workspace import AutonomyWorkspace

_SMOKE_SCRIPT = (
    "import json, sys\n"
    "paths = [arg for arg in sys.argv[1:] if arg.startswith('/workspace/')]\n"
    "loaded = [json.load(open(path, encoding='utf-8')) for path in paths]\n"
    "print(json.dumps({'smoke': 'PASS', 'inputs': len(loaded)}))\n"
)


class _NoBrokerToolbox:
    def manifest(self) -> list[dict[str, Any]]:
        return []

    def execute(self, request: ResearchRequest, bundle: Any) -> ResearchResult:
        raise RuntimeError("smoke check must not reach the broker toolbox")


def _request(tool: ResearchTool, arguments: dict[str, Any], rid: str) -> ResearchRequest:
    return ResearchRequest(request_id=rid, tool=tool, arguments=arguments, purpose="host smoke check")


def run_research_toolchain_smoke(
    workspace_root: str | Path,
    *,
    sandbox: Any,
    quantconnect: QuantConnectMediator | None = None,
) -> dict[str, Any]:
    workspace = AutonomyWorkspace(Path(workspace_root), sandbox=sandbox)
    toolbox = AutonomyToolbox(_NoBrokerToolbox(), workspace, quantconnect=quantconnect)
    history = [{
        "round": 1,
        "type": "research_result",
        "payload": ResearchResult(
            request_id="smoke-bars", tool=ResearchTool.HISTORICAL_BARS, success=True,
            data={"bars": [{"close": 1.0}, {"close": 1.1}]},
        ).model_dump(mode="json"),
    }]
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, tool: ResearchTool, arguments: dict[str, Any], expect=None) -> None:
        try:
            result = toolbox.execute_with_history(_request(tool, arguments, name.lower()), None, history)
            passed = result.success and (expect is None or expect(result.data))
            checks[name] = {
                "status": "PASS" if passed else "FAIL",
                "error": None if passed else (result.error or "unexpected result"),
            }
        except Exception as exc:  # the smoke report itself must never raise
            checks[name] = {"status": "FAIL", "error": f"{type(exc).__name__}:{exc}"[:300]}

    check("WORKSPACE_WRITE", ResearchTool.WORKSPACE,
          {"operation": "write", "path": "tools/host_smoke.py", "content": _SMOKE_SCRIPT})
    check("WORKSPACE_READ", ResearchTool.WORKSPACE,
          {"operation": "read", "path": "tools/host_smoke.py"},
          lambda data: data.get("content") == _SMOKE_SCRIPT)
    check("WORKSPACE_ALIAS_ACTION", ResearchTool.WORKSPACE,
          {"action": "READ", "path": "tools/host_smoke.py"},
          lambda data: data.get("content") == _SMOKE_SCRIPT)
    check("WORKSPACE_LIST", ResearchTool.WORKSPACE, {"operation": "list"},
          lambda data: any(item["path"] == "tools/host_smoke.py" for item in data.get("artifacts", [])))
    check("RUN_RESEARCH_SCRIPT", ResearchTool.RUN_RESEARCH_SCRIPT,
          {"script_path": "tools/host_smoke.py", "args": [], "timeout_seconds": 30})
    check("RUN_RESEARCH_SCRIPT_INPUTS", ResearchTool.RUN_RESEARCH_SCRIPT,
          {"path": "tools/host_smoke.py", "input_request_ids": ["smoke-bars"], "timeout_seconds": 30})
    check("QUANTCONNECT_STATUS", ResearchTool.QUANTCONNECT, {"action": "STATUS"},
          lambda data: "HOME" not in str(data.get("stderr") or "")
          and "home directory" not in str(data.get("stderr") or "").lower())
    check("WORKSPACE_DELETE", ResearchTool.WORKSPACE,
          {"operation": "delete", "path": "tools/host_smoke.py"})
    return {
        "schema": "RESEARCH_TOOLCHAIN_SMOKE_V1",
        "status": "PASS" if all(item["status"] == "PASS" for item in checks.values()) else "FAIL",
        "workspace_root": str(Path(workspace_root)),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    from .research_sandbox import WSLResearchSandbox

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--workspace", required=True, help="throw-away workspace directory")
    args = parser.parse_args(argv)
    report = run_research_toolchain_smoke(
        args.workspace, sandbox=WSLResearchSandbox(repo_root=args.repo_root)
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
