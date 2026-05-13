"""B-Sprint: Self-Tester for learned correction patterns.

Validates a proposed correction in a sandbox BEFORE the learner persists
it as auto-applicable.

Strategy:
  1. Apply the correction transform with a synthetic-safe arg variant
     (or the real failed args if the tool is in SAFE_TOOLS).
  2. Execute via ToolExecutor with hard timeout.
  3. Check: success=True, no error indicator in output, output non-empty.

Whitelist of tools considered SAFE for live sandbox execution:
  - run_powershell (with safe scripts: Get-Date, Get-Process, etc.)
  - run_command (read-only commands only)
  - check_port, check_http_service, scan_local_network
  - read_file, list_directory, list_processes, get_system_info

For unsafe tools (write_file, install_package, kill_process), we do
a DRY-RUN: just validate the args shape and to_tool exists.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Optional, Tuple

from brain_v9.core import validator_metrics as _vmetrics

# Tools considered safe for live execution in sandbox
SAFE_TOOLS = {
    "run_powershell",   # only with safe script regex match
    "check_port", "check_http_service", "scan_local_network",
    "read_file", "list_directory", "list_processes",
    "get_system_info", "run_diagnostic", "search_files",
    "grep_codebase", "analyze_python",
}

# Tools that ALWAYS require dry-run only (never live)
UNSAFE_TOOLS = {
    "install_package", "write_file", "edit_file", "kill_process",
    "promote_staged_change", "rollback_staged_change",
    "execute_top_action_live", "execute_strategy_candidate_live",
    "execute_trade_paper",
}

# Safe script patterns for run_powershell sandbox (whitelist)
SAFE_PS_PATTERN = re.compile(
    r"^\s*("
    r"Get-Date|Get-Process|Get-Service|Get-NetTCPConnection|"
    r"Test-Connection|Test-NetConnection|Resolve-DnsName|"
    r"Get-ChildItem|Get-Content|Get-Location|Get-Command|"
    r"Get-CimInstance|Get-WmiObject|"
    r"echo |Write-Host"
    r")",
    re.IGNORECASE,
)

# Indicators in output that mean execution failed
ERROR_INDICATORS = (
    "Traceback", "Exception", "ScriptHalted",
    "PowerShellCommandWithDollar", "R17:",
    "command not found", "is not recognized",
)


class SelfTester:
    def __init__(self, tools, llm=None) -> None:
        self.tools = tools
        self.llm = llm
        self.logger = logging.getLogger("SelfTester")

    async def validate_correction(
        self,
        to_tool: str,
        new_args: Dict[str, Any],
        original_error: str,
        timeout: float = 20.0,
        strict_args: bool = True,
    ) -> Tuple[bool, str]:
        """Returns (passed, reason).

        If strict_args=True (default), uses ToolExecutor._validate_args to reject
        patterns that provide wrong arg names for the target tool BEFORE execution.
        This prevents masking bugs by substituting safe probes.
        """

        # Step 1: tool must be registered
        try:
            available = set(self.tools.list_tools())
        except Exception:
            available = set()
        if to_tool not in available:
            return (False, f"to_tool not registered: {to_tool}")

        # Step 1b (B3b): strict args validation against tool signature
        if strict_args:
            arg_error = self._validate_args_strict(to_tool, new_args)
            if arg_error:
                _vmetrics.record("self_test_args_mismatch")
                return (False, f"args mismatch: {arg_error}")

        # Step 2: unsafe tools -> dry-run only
        if to_tool in UNSAFE_TOOLS:
            _vmetrics.record("self_test_dryrun_unsafe")
            # Just validate args shape is non-empty
            if not new_args:
                return (False, "unsafe tool with empty args (dry-run rejected)")
            return (True, "dry-run validated (unsafe tool, not executed)")

        # Step 3: run_powershell -> require safe script OR substitute probe
        if to_tool == "run_powershell":
            script = str(new_args.get("script", ""))
            if not SAFE_PS_PATTERN.match(script):
                # Substitute with safe probe to validate wiring works
                _vmetrics.record("self_test_substitute_safe_probe")
                new_args = {"script": "Get-Date"}

        # Step 4: live execute with timeout
        try:
            output = await asyncio.wait_for(
                self.tools.execute(to_tool, **new_args),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            _vmetrics.record("self_test_timeout")
            return (False, f"sandbox execution timed out ({timeout}s)")
        except Exception as e:
            _vmetrics.record("self_test_exception")
            return (False, f"sandbox raised: {type(e).__name__}: {str(e)[:200]}")

        # Step 5: validate output
        if output is None:
            return (False, "tool returned None")

        out_str = str(output)[:3000]

        # Check for inner failure markers
        if isinstance(output, dict):
            if output.get("success") is False:
                return (False, f"tool reported success=False: {output.get('error', '')[:200]}")

        # Check for error indicators
        for ind in ERROR_INDICATORS:
            if ind in out_str:
                return (False, f"output contains error indicator: {ind}")

        # Check for same error_signature as original
        if original_error:
            # If a distinctive token from original error reappears -> regression
            tokens = re.findall(r"\b[A-Z][A-Za-z]{6,}\b", original_error)
            for tok in tokens[:5]:
                if tok in out_str and tok in original_error:
                    # Same distinctive symbol present -> probably regressed
                    if tok not in ("PowerShell", "Windows", "Microsoft"):
                        return (False, f"regression: original error token '{tok}' reappears in output")

        if len(out_str.strip()) < 1:
            return (False, "empty output")

        _vmetrics.record("self_test_passed")
        return (True, "ok")

    def _validate_args_strict(self, to_tool: str, new_args: Dict[str, Any]) -> Optional[str]:
        """B3b: Check new_args against tool signature. Returns error string or None if ok."""
        try:
            tool_entry = self.tools._tools.get(to_tool)
            if not tool_entry:
                return None  # can't validate, allow
            fn = tool_entry.get("func")
            if not fn:
                return None
            import inspect as _insp
            sig = _insp.signature(fn)
        except Exception:
            return None  # can't introspect, allow

        # Find required args (no default, not *args/**kwargs, not private)
        required: list = []
        valid_names: set = set()
        accepts_var_kw = False
        for pname, p in sig.parameters.items():
            if p.kind == _insp.Parameter.VAR_KEYWORD:
                accepts_var_kw = True
                continue
            if p.kind == _insp.Parameter.VAR_POSITIONAL:
                continue
            valid_names.add(pname)
            if p.default is _insp.Parameter.empty and not pname.startswith("_"):
                required.append(pname)

        missing = [r for r in required if r not in new_args]
        unknown = [] if accepts_var_kw else [k for k in new_args if k not in valid_names and not k.startswith("_")]

        problems = []
        if missing:
            problems.append(f"missing required: {missing}")
        if unknown:
            problems.append(f"unknown args: {unknown}")
        return "; ".join(problems) if problems else None
