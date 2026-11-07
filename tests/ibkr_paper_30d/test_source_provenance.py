from __future__ import annotations

import inspect
import json

from ibkr_paper_30d.autonomous_research import (
    AutonomousResearchLoop,
    CodexAutonomousCLIProvider,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.source_provenance import (
    native_tool_provenance,
    research_source_provenance,
)

REQUESTED = "2026-11-07T15:00:00Z"
RECEIVED = "2026-11-07T15:00:02Z"


def _record(tool, arguments, data, success=True):
    request = ResearchRequest(request_id="r1", tool=tool, arguments=arguments, purpose="p")
    result = ResearchResult(request_id="r1", tool=tool, success=success, data=data)
    return research_source_provenance(request, result, requested_at_utc=REQUESTED, received_at_utc=RECEIVED)


def test_news_provenance_preserves_headline_provider_article_and_timestamp() -> None:
    data = {
        "contract": {"symbol": "ENS", "conId": 1},
        "headlines": [
            {"time": "2026-11-07 14:30:00+00:00", "providerCode": "DJ-N", "articleId": "DJ-N$1",
             "headline": "EnerSys to acquire"},
        ],
    }

    record = _record(ResearchTool.NEWS_SEARCH, {"symbol": "ENS"}, data)

    assert record["provider"] == "IBKR_TWS_API"
    assert record["tool"] == "NEWS_SEARCH"
    assert record["symbol"] == "ENS"
    assert record["source_role"] == "SECONDARY"
    assert record["source_ids"] == ["DJ-N$1"]
    assert record["news_items"][0] == {
        "provider_code": "DJ-N", "article_id": "DJ-N$1", "headline": "EnerSys to acquire",
        "time": "2026-11-07 14:30:00+00:00",
    }
    assert record["source_timestamp_utc"] == "2026-11-07T14:30:00Z"
    assert record["freshness_seconds"] == 1802
    assert record["requested_at_utc"] == REQUESTED and record["received_at_utc"] == RECEIVED
    assert record["payload_sha256"] == sha256_json(data)
    assert record["query"] == {"symbol": "ENS"}
    assert record["url"] is None


def test_broker_market_data_is_primary_and_unknown_timestamp_is_not_invented() -> None:
    record = _record(ResearchTool.HISTORICAL_BARS, {"symbol": "SOL"}, {"bars": [{"close": 1}]})

    assert record["source_role"] == "PRIMARY"
    assert record["source_timestamp_utc"] is None
    assert record["freshness_seconds"] is None
    assert "SOURCE_TIMESTAMP_UNAVAILABLE" in record["limitations"]


def test_naive_source_time_is_kept_raw_without_freshness() -> None:
    record = _record(ResearchTool.HISTORICAL_BARS, {"symbol": "SOL"},
                     {"bars": [{"date": "2026-11-07 09:30:00", "close": 1}]})

    assert record["source_timestamp_raw"] == "2026-11-07 09:30:00"
    assert record["freshness_seconds"] is None
    assert "SOURCE_TIMEZONE_UNKNOWN" in record["limitations"]


def test_workspace_and_scripts_are_labelled_derived() -> None:
    record = _record(ResearchTool.RUN_RESEARCH_SCRIPT, {"path": "tools/a.py"}, {"status": "COMPLETED"})

    assert record["provider"] == "HOST_RESEARCH_SANDBOX"
    assert record["source_role"] == "DERIVED"


def test_query_is_bounded_and_hashed() -> None:
    record = _record(ResearchTool.WORKSPACE, {"operation": "write", "content": "x" * 10_000}, {})

    assert len(json.dumps(record["query"])) < 2_500
    assert record["query_sha256"] == sha256_json({"operation": "write", "content": "x" * 10_000})


def test_native_web_search_records_query_when_exposed_and_never_invents_urls() -> None:
    exposed = native_tool_provenance([{"type": "web_search", "status": "completed", "id": "w1",
                                       "query": "EnerSys Ultralife"}])
    hidden = native_tool_provenance([{"type": "web_search", "status": "completed", "id": "w2"}])

    assert exposed[0]["query"] == "EnerSys Ultralife"
    assert exposed[0]["trace_status"] == "QUERY_RECORDED_URLS_UNAVAILABLE"
    assert exposed[0]["urls"] == []
    assert hidden[0]["trace_status"] == "WEB_SOURCE_TRACE_UNAVAILABLE"
    assert hidden[0]["query"] is None


def test_native_tool_events_keep_query_and_urls_from_codex_stream() -> None:
    stream = "\n".join([
        json.dumps({"type": "item.completed", "item": {"type": "web_search", "id": "w1",
                                                       "status": "completed", "query": "ENS ULBI deal"}}),
        json.dumps({"type": "item.completed", "item": {"type": "web_search", "id": "w2",
                                                       "action": {"type": "open_page", "url": "https://example.com/a"}}}),
    ])

    events = CodexAutonomousCLIProvider._native_tool_events(stream)

    assert events[0]["query"] == "ENS ULBI deal"
    assert events[1]["urls"] == ["https://example.com/a"]


def test_research_loop_records_provenance_and_provider_prompt_excludes_it() -> None:
    loop_source = inspect.getsource(AutonomousResearchLoop.run)
    provider_source = inspect.getsource(CodexAutonomousCLIProvider)

    assert "research_source_provenance(" in loop_source
    assert "native_tool_provenance(" in loop_source
    assert "model_visible_history(" in provider_source


def test_news_search_reads_requested_article_bodies_and_reports_failures() -> None:
    from types import SimpleNamespace

    from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox

    class FakeIB:
        def __init__(self):
            self.article_calls = []

        def reqNewsProviders(self):
            return [SimpleNamespace(code="DJ-N", name="Dow Jones")]

        def reqHistoricalNews(self, con_id, providers, start, end, total):
            return [SimpleNamespace(time="2026-11-07 14:30:00+00:00", providerCode="DJ-N",
                                    articleId="DJ-N$1", headline="EnerSys to acquire")]

        def reqNewsArticle(self, provider_code, article_id):
            self.article_calls.append((provider_code, article_id))
            if article_id == "DJ-N$missing":
                raise RuntimeError("not entitled")
            return SimpleNamespace(articleType=0, articleText="Body " * 5000)

        def disconnect(self):
            pass

    ib = FakeIB()
    toolbox = object.__new__(IBKRResearchToolbox)
    toolbox._connect = lambda: ib
    toolbox._qualify = lambda _ib, _args: SimpleNamespace(conId=1)
    toolbox._serialize_contract = lambda contract: {"conId": 1, "symbol": "ENS"}

    data = toolbox._news_search({"symbol": "ENS", "article_ids": ["DJ-N$1", "DJ-N$missing"]})

    assert ib.article_calls == [("DJ-N", "DJ-N$1"), ("DJ-N", "DJ-N$missing")]
    retrieved, failed = data["articles"]
    assert retrieved["status"] == "RETRIEVED" and len(retrieved["text"]) <= 8000
    assert retrieved["truncated"] is True
    assert failed["status"] == "UNAVAILABLE" and failed["error_type"] == "RuntimeError"
    assert data["headlines"][0]["articleId"] == "DJ-N$1"


def test_news_search_without_article_ids_does_not_fetch_bodies() -> None:
    from types import SimpleNamespace

    from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox

    class FakeIB:
        def reqNewsProviders(self):
            return []

        def reqHistoricalNews(self, *args):
            return []

        def reqNewsArticle(self, *args):
            raise AssertionError("article bodies must only be read on request")

        def disconnect(self):
            pass

    toolbox = object.__new__(IBKRResearchToolbox)
    toolbox._connect = lambda: FakeIB()
    toolbox._qualify = lambda _ib, _args: SimpleNamespace(conId=1)
    toolbox._serialize_contract = lambda contract: {"conId": 1}

    data = toolbox._news_search({"symbol": "ENS"})

    assert "articles" not in data