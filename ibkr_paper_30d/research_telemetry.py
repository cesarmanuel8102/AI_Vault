from __future__ import annotations

import time
from typing import Any


RESEARCH_TELEMETRY_SCHEMA = "CODEX_RESEARCH_TELEMETRY_V1"
TELEMETRY_SOURCE = "SYSTEM_GENERATED"

_TOOL_SCANNER = "MARKET_SCANNER"
_TOOL_RESOLVE_CONTRACT = "RESOLVE_CONTRACT"
_TOOL_OPTION_CHAIN = "OPTION_CHAIN"
_TOOL_QUOTE = "QUOTE"
_TOOL_HISTORICAL_BARS = "HISTORICAL_BARS"
_TOOL_BROKER_FEASIBILITY = "BROKER_FEASIBILITY"
_TOOL_NEWS_SEARCH = "NEWS_SEARCH"


class ResearchTelemetryAccumulator:
    """Objective research telemetry derived from actual tool execution.

    Counters increment only when the host executes a research request through
    the toolbox. Model narratives, reasoning summaries and claimed reason codes
    never contribute: the LLM cannot prove its own research quality by text.

    This module deliberately avoids importing the research loop so telemetry
    stays a leaf observer; requests and results are consumed structurally.
    """

    def __init__(self) -> None:
        self._started_monotonic = time.monotonic()
        self._requests_executed = 0
        self._tools_used: set[str] = set()
        self._scanner_queries = 0
        self._scanner_results = 0
        self._symbols: set[str] = set()
        self._asset_classes: set[str] = set()
        self._option_chains = 0
        self._price_snapshots = 0
        self._historical_requests = 0
        self._market_data_requests = 0
        self._feasibility_checks = 0
        self._blocked = 0
        self._symbol_tools: dict[str, set[str]] = {}

    def observe_request(self, request: Any) -> None:
        """Record that the host is about to execute a real tool request."""

    def observe_result(self, result: Any) -> None:
        self._requests_executed += 1
        raw_tool = getattr(result, "tool", "")
        tool = str(getattr(raw_tool, "value", raw_tool) or "")
        self._tools_used.add(tool)
        data = dict(getattr(result, "data", None) or {})
        if not bool(getattr(result, "success", False)):
            self._blocked += 1
        if tool == _TOOL_SCANNER:
            self._scanner_queries += 1
            rows = data.get("results") or []
            self._scanner_results += len(rows)
            for row in rows:
                contract = row.get("contract") or {}
                symbol = str(
                    contract.get("symbol") or row.get("symbol") or ""
                ).upper()
                if symbol:
                    self._symbols.add(symbol)
                    self._symbol_tools.setdefault(symbol, set()).add(tool)
        elif tool == _TOOL_RESOLVE_CONTRACT:
            for contract in data.get("contracts") or []:
                symbol = str(contract.get("symbol") or "").upper()
                sec_type = str(contract.get("secType") or "").upper()
                if symbol:
                    self._symbols.add(symbol)
                    self._symbol_tools.setdefault(symbol, set()).add(tool)
                if sec_type:
                    self._asset_classes.add(sec_type)
        elif tool == _TOOL_OPTION_CHAIN:
            self._option_chains += 1
            underlying = data.get("underlying") or {}
            symbol = str(underlying.get("symbol") or "").upper()
            if symbol:
                self._symbols.add(symbol)
                self._symbol_tools.setdefault(symbol, set()).add(tool)
        elif tool == _TOOL_QUOTE:
            self._price_snapshots += 1
            self._market_data_requests += 1
            self._observe_contract_data(data)
        elif tool == _TOOL_HISTORICAL_BARS:
            self._historical_requests += 1
            self._market_data_requests += 1
            self._observe_contract_data(data)
        elif tool == _TOOL_BROKER_FEASIBILITY:
            self._feasibility_checks += 1
            self._observe_contract_data(data)
        elif tool == _TOOL_NEWS_SEARCH:
            self._observe_contract_data(data)

    def _observe_contract_data(self, data: dict[str, Any]) -> None:
        contract = data.get("contract") or {}
        symbol = str(contract.get("symbol") or "").upper()
        if symbol:
            self._symbols.add(symbol)
            self._symbol_tools.setdefault(symbol, set()).add("CONTRACT")

    def summary(self) -> dict[str, Any]:
        deeply_analyzed = sorted(
            symbol
            for symbol, tools in self._symbol_tools.items()
            if len(tools) >= 2
        )
        return {
            "schema": RESEARCH_TELEMETRY_SCHEMA,
            "telemetry_source": TELEMETRY_SOURCE,
            "research_requests_executed": self._requests_executed,
            "tools_used": sorted(self._tools_used),
            "scanner_queries": self._scanner_queries,
            "scanner_results_received": self._scanner_results,
            "contracts_resolved": len(
                {
                    symbol
                    for symbol, tools in self._symbol_tools.items()
                    if _TOOL_RESOLVE_CONTRACT in tools
                }
            ),
            "symbols_examined": sorted(self._symbols),
            "asset_classes_examined": sorted(self._asset_classes),
            "option_chains_queried": self._option_chains,
            "price_snapshot_requests": self._price_snapshots,
            "historical_data_requests": self._historical_requests,
            "market_data_requests": self._market_data_requests,
            "candidates_generated": len(self._symbols),
            "candidates_deeply_analyzed": deeply_analyzed,
            "feasibility_checks": self._feasibility_checks,
            "blocked_requests": self._blocked,
            "research_elapsed_ms": int(
                (time.monotonic() - self._started_monotonic) * 1000
            ),
        }


def build_telemetry_summary_from_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild telemetry by replaying executed research results in a transcript.

    Only 'research_result' events (host-executed tool calls) contribute.
    Model turns, native tool activity and narratives are ignored.
    """

    class _ReplayResult:
        def __init__(self, payload: dict[str, Any]) -> None:
            raw_tool = payload.get("tool") or ""
            self.tool = str(getattr(raw_tool, "value", raw_tool) or "")
            self.success = bool(payload.get("success"))
            self.data = dict(payload.get("data") or {})

    accumulator = ResearchTelemetryAccumulator()
    for event in history:
        if event.get("type") != "research_result":
            continue
        payload = event.get("payload") or {}
        accumulator.observe_result(_ReplayResult(payload))
    return accumulator.summary()


def classify_research_depth(summary: dict[str, Any]) -> str:
    """Descriptive depth label for reports. Never a gate, quota or target."""

    executed = int(summary.get("research_requests_executed") or 0)
    tools = len(summary.get("tools_used") or [])
    if executed == 0:
        return "MINIMAL"
    if tools <= 1:
        return "SINGLE_TOOL"
    return "MULTI_TOOL"