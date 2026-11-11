from fetch_qc_trace_logs import fetch_trace_lines, parse_trace_lines


def test_parse_trace_lines_keeps_only_valid_trace_payloads():
    lines = [
        "2023-01-01 10:00:00 TRACE|{\"type\":\"entry\",\"ticker\":\"SPY\"}",
        "2023-01-01 10:01:00 ordinary message",
        "TRACE|not-json",
        "2023-01-01 10:03:00 TRACE|{\"type\":\"checkpoint\",\"checkpoint\":3}",
    ]
    assert parse_trace_lines(lines) == [
        {"type": "entry", "ticker": "SPY"},
        {"type": "checkpoint", "checkpoint": 3},
    ]


def test_fetch_trace_lines_paginates_filtered_results(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    pages = [
        Response({"success": True, "length": 201, "logs": ["TRACE|{}"] * 200}),
        Response({"success": True, "length": 201, "logs": ["TRACE|{}"]}),
    ]

    def post(url, headers, json, timeout):
        calls.append(json)
        return pages.pop(0)

    monkeypatch.setattr("fetch_qc_trace_logs.requests.post", post)
    result = fetch_trace_lines(123, "backtest", {"user-id": "u", "api-token": "t"})

    assert len(result) == 201
    assert [call["start"] for call in calls] == [0, 200]
    assert all(call["query"] == "TRACE|" for call in calls)
