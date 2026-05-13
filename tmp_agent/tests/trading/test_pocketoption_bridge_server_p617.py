"""
Tests for brain_v9.trading.pocketoption_bridge_server (P6-17)

Covers:
- Pure functions: utc_now, normalize_symbol, build_row
- State management: ensure_room_files, read_commands, write_commands, append_event, update_feed
- Command queue: create_command, next_pending_command, command_status, register_command_result
- FastAPI endpoints via TestClient
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import brain_v9.trading.pocketoption_bridge_server as mod


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def bridge_paths(tmp_path, monkeypatch):
    """Redirect all module-level path constants to tmp_path subdirectories."""
    room = tmp_path / "room"
    room.mkdir()
    monkeypatch.setattr(mod, "ROOM_DIR", room)
    monkeypatch.setattr(mod, "LATEST_PATH", room / "latest.json")
    monkeypatch.setattr(mod, "FEED_PATH", room / "feed.json")
    monkeypatch.setattr(mod, "EVENTS_PATH", room / "events.ndjson")
    monkeypatch.setattr(mod, "COMMANDS_PATH", room / "commands.json")
    monkeypatch.setattr(mod, "LAST_COMMAND_PATH", room / "last_cmd.json")
    monkeypatch.setattr(mod, "LAST_RESULT_PATH", room / "last_result.json")
    # Reset the global _FEED_CACHE so each test starts with clean state
    monkeypatch.setattr(mod, "_FEED_CACHE", None)
    return room


@pytest.fixture
def setup_room(bridge_paths):
    """Ensure room files are created after path redirection."""
    mod.ensure_room_files()
    return bridge_paths


@pytest.fixture
def client(bridge_paths):
    """Create a TestClient after monkeypatching paths."""
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


# ═══════════════════════════════════════════════════════════════════════════════
# PURE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestUtcNow:
    def test_utc_now_returns_string(self):
        result = mod.utc_now()
        assert isinstance(result, str)

    def test_utc_now_ends_with_z(self):
        result = mod.utc_now()
        assert result.endswith("Z")

    def test_utc_now_no_microseconds(self):
        result = mod.utc_now()
        # ISO format with microseconds would have a dot; without should not
        assert "." not in result

    def test_utc_now_is_valid_iso(self):
        result = mod.utc_now()
        # Should match pattern like 2026-03-26T12:00:00Z
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_utc_now_no_plus_offset(self):
        result = mod.utc_now()
        assert "+00:00" not in result


class TestNormalizeSymbol:
    def test_none_input(self):
        assert mod.normalize_symbol(None) == (None, None)

    def test_empty_string(self):
        assert mod.normalize_symbol("") == (None, None)

    def test_zero_input(self):
        assert mod.normalize_symbol(0) == (None, None)

    def test_simple_pair(self):
        symbol, pair = mod.normalize_symbol("EURUSD")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_lowercase_pair(self):
        symbol, pair = mod.normalize_symbol("eurusd")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_already_otc_suffix(self):
        symbol, pair = mod.normalize_symbol("eurusd_otc")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_uppercase_otc_suffix(self):
        symbol, pair = mod.normalize_symbol("EURUSDOTC")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_mixed_case_otc(self):
        symbol, pair = mod.normalize_symbol("EURUSDOtc")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_with_slash(self):
        symbol, pair = mod.normalize_symbol("EUR/USD")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_with_spaces(self):
        symbol, pair = mod.normalize_symbol("EUR USD")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_with_slash_and_otc(self):
        symbol, pair = mod.normalize_symbol("EUR/USD_otc")
        assert symbol == "EURUSD_otc"
        assert pair == "EURUSD OTC"

    def test_gbpjpy(self):
        symbol, pair = mod.normalize_symbol("GBPJPY")
        assert symbol == "GBPJPY_otc"
        assert pair == "GBPJPY OTC"

    def test_integer_input_truthy(self):
        # e.g. 123 is truthy, converts via str()
        symbol, pair = mod.normalize_symbol(123)
        assert symbol == "123_otc"
        assert pair == "123 OTC"


class TestBuildRow:
    def test_minimal_payload_current_only(self):
        payload = {"current": {"symbol": "EURUSD", "price": 1.1234}}
        row = mod.build_row(payload)
        assert row["symbol"] == "EURUSD_otc"
        assert row["price"] == 1.1234
        assert "captured_utc" in row

    def test_full_payload(self):
        payload = {
            "captured_utc": "2026-01-01T00:00:00Z",
            "current": {
                "symbol": "EURUSD",
                "pair": "EUR/USD OTC",
                "price": 1.1234,
                "source_timestamp": "2026-01-01T00:00:00.000Z",
                "payout_pct": 85,
                "expiry_seconds": 60,
            },
            "runtime": {"captured_utc": "2026-01-01T00:00:00Z"},
            "ws": {
                "event_count": 42,
                "last_event_name": "candles",
                "last_socket_url": "wss://example.com",
                "last_stream_symbol": "EURUSD_otc",
                "visible_symbol": "EUR/USD OTC",
                "stream_symbol_match": True,
            },
            "dom": {
                "pair": "EUR/USD OTC",
                "balance_demo": 10000.0,
                "visible_price": "1.1234",
                "selected_duration_label": "1m",
                "duration_candidates": ["30s", "1m", "5m"],
                "indicator_candidates": ["RSI", "MACD"],
                "indicator_readouts": [{"name": "RSI", "value": 55}],
                "payout_pct": 85,
                "expiry_seconds": 60,
            },
        }
        row = mod.build_row(payload)
        assert row["captured_utc"] == "2026-01-01T00:00:00Z"
        assert row["pair"] == "EUR/USD OTC"
        assert row["symbol"] == "EURUSD_otc"
        assert row["price"] == 1.1234
        assert row["payout_pct"] == 85
        assert row["expiry_seconds"] == 60
        assert row["socket_event_count"] == 42
        assert row["last_socket_event"] == "candles"
        assert row["last_socket_url"] == "wss://example.com"
        assert row["last_stream_symbol"] == "EURUSD_otc"
        assert row["visible_symbol"] == "EUR/USD OTC"
        assert row["stream_symbol_match"] is True
        assert row["balance_demo"] == 10000.0
        assert row["visible_price"] == "1.1234"
        assert row["selected_duration_label"] == "1m"
        assert row["duration_candidates"] == ["30s", "1m", "5m"]
        assert row["indicator_candidates"] == ["RSI", "MACD"]
        assert row["duration_candidates_count"] == 3
        assert row["indicator_candidates_count"] == 2
        assert row["indicator_readouts_count"] == 1

    def test_missing_sections_default_gracefully(self):
        payload = {}
        row = mod.build_row(payload)
        assert row["symbol"] is None
        assert row["pair"] is None
        assert row["price"] is None
        assert row["duration_candidates"] == []
        assert row["indicator_candidates"] == []
        assert row["duration_candidates_count"] == 0
        assert row["indicator_candidates_count"] == 0
        assert row["indicator_readouts_count"] == 0

    def test_duration_candidates_extracted(self):
        payload = {"dom": {"duration_candidates": ["30s", "1m", "5m", "15m"]}}
        row = mod.build_row(payload)
        assert row["duration_candidates"] == ["30s", "1m", "5m", "15m"]
        assert row["duration_candidates_count"] == 4

    def test_indicator_candidates_extracted(self):
        payload = {"dom": {"indicator_candidates": ["RSI", "MACD", "Bollinger"]}}
        row = mod.build_row(payload)
        assert row["indicator_candidates"] == ["RSI", "MACD", "Bollinger"]
        assert row["indicator_candidates_count"] == 3

    def test_price_fallback_current_price(self):
        payload = {"current": {"price": 1.5}}
        row = mod.build_row(payload)
        assert row["price"] == 1.5

    def test_price_fallback_last_price(self):
        payload = {"current": {"last_price": 1.6}}
        row = mod.build_row(payload)
        assert row["price"] == 1.6

    def test_price_fallback_dom_visible_price(self):
        payload = {"current": {}, "dom": {"visible_price": "1.7"}}
        row = mod.build_row(payload)
        assert row["price"] == "1.7"

    def test_symbol_from_current_symbol(self):
        payload = {"current": {"symbol": "GBPJPY"}}
        row = mod.build_row(payload)
        assert row["symbol"] == "GBPJPY_otc"

    def test_symbol_from_current_pair(self):
        payload = {"current": {"pair": "USDJPY"}}
        row = mod.build_row(payload)
        assert row["symbol"] == "USDJPY_otc"

    def test_symbol_from_dom_pair(self):
        payload = {"current": {}, "dom": {"pair": "AUDUSD"}}
        row = mod.build_row(payload)
        assert row["symbol"] == "AUDUSD_otc"

    def test_non_dict_current_falls_back_to_payload(self):
        payload = {"current": "not_a_dict", "symbol": "NZDUSD", "price": 0.65}
        row = mod.build_row(payload)
        assert row["symbol"] == "NZDUSD_otc"
        assert row["price"] == 0.65

    def test_non_dict_dom_defaults_empty(self):
        payload = {"dom": "not_a_dict", "current": {"symbol": "EURUSD"}}
        row = mod.build_row(payload)
        assert row["duration_candidates"] == []
        assert row["balance_demo"] is None

    def test_captured_utc_from_payload(self):
        payload = {"captured_utc": "2026-06-01T00:00:00Z"}
        row = mod.build_row(payload)
        assert row["captured_utc"] == "2026-06-01T00:00:00Z"

    def test_captured_utc_from_runtime(self):
        payload = {"runtime": {"captured_utc": "2026-06-02T00:00:00Z"}}
        row = mod.build_row(payload)
        assert row["captured_utc"] == "2026-06-02T00:00:00Z"

    def test_captured_utc_falls_back_to_utc_now(self):
        payload = {}
        row = mod.build_row(payload)
        assert row["captured_utc"].endswith("Z")

    def test_balance_from_dom(self):
        payload = {"dom": {"balance_demo": 5000.0}}
        row = mod.build_row(payload)
        assert row["balance_demo"] == 5000.0

    def test_balance_fallback_from_payload(self):
        payload = {"balance_demo": 3000.0}
        row = mod.build_row(payload)
        assert row["balance_demo"] == 3000.0

    def test_non_list_duration_candidates_defaults_empty(self):
        payload = {"dom": {"duration_candidates": "invalid"}}
        row = mod.build_row(payload)
        assert row["duration_candidates"] == []
        assert row["duration_candidates_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# STATE MANAGEMENT (tmp_path)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnsureRoomFiles:
    def test_creates_directory_and_files(self, bridge_paths):
        # Remove the room dir that the fixture created so ensure_room_files
        # can prove it creates everything from scratch
        import shutil
        shutil.rmtree(bridge_paths)
        assert not bridge_paths.exists()
        mod.ensure_room_files()
        assert bridge_paths.exists()
        assert (bridge_paths / "feed.json").exists()
        assert (bridge_paths / "commands.json").exists()

    def test_idempotent_second_call(self, bridge_paths):
        mod.ensure_room_files()
        feed1 = (bridge_paths / "feed.json").read_text(encoding="utf-8")
        mod.ensure_room_files()
        feed2 = (bridge_paths / "feed.json").read_text(encoding="utf-8")
        assert feed1 == feed2

    def test_feed_has_correct_schema(self, bridge_paths):
        mod.ensure_room_files()
        feed = json.loads((bridge_paths / "feed.json").read_text(encoding="utf-8"))
        assert feed["schema_version"] == "pocketoption_browser_bridge_normalized_feed_v1"
        assert feed["row_count"] == 0
        assert feed["rows"] == []
        assert feed["last_row"] is None

    def test_commands_has_correct_schema(self, bridge_paths):
        mod.ensure_room_files()
        cmds = json.loads((bridge_paths / "commands.json").read_text(encoding="utf-8"))
        assert cmds["schema_version"] == "pocketoption_browser_bridge_commands_v1"
        assert cmds["commands"] == []


class TestReadCommands:
    def test_returns_default_when_no_file(self, bridge_paths):
        result = mod.read_commands()
        assert result["schema_version"] == "pocketoption_browser_bridge_commands_v1"
        assert result["commands"] == []

    def test_returns_content_when_file_exists(self, setup_room):
        cmds = mod.read_commands()
        cmds["commands"].append({"command_id": "test1"})
        mod.write_commands(cmds)

        result = mod.read_commands()
        assert len(result["commands"]) == 1
        assert result["commands"][0]["command_id"] == "test1"


class TestWriteCommands:
    def test_writes_and_adds_updated_utc(self, setup_room):
        payload = {"commands": [], "schema_version": "v1"}
        mod.write_commands(payload)
        assert "updated_utc" in payload
        assert payload["updated_utc"].endswith("Z")

    def test_file_is_written(self, setup_room):
        payload = {"commands": [{"id": "x"}], "schema_version": "v1"}
        mod.write_commands(payload)
        raw = json.loads(mod.COMMANDS_PATH.read_text(encoding="utf-8"))
        assert raw["commands"][0]["id"] == "x"


class TestAppendEvent:
    def test_appends_ndjson_line(self, setup_room):
        events_path = mod.EVENTS_PATH
        events_path.write_text("", encoding="utf-8")
        mod.append_event({"type": "test", "data": 123})
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert "captured_utc" in event
        assert event["payload"]["type"] == "test"

    def test_multiple_appends(self, setup_room):
        events_path = mod.EVENTS_PATH
        events_path.write_text("", encoding="utf-8")
        mod.append_event({"n": 1})
        mod.append_event({"n": 2})
        mod.append_event({"n": 3})
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3


class TestUpdateFeed:
    def test_adds_row(self, setup_room):
        row = {"captured_utc": "2026-01-01T00:00:00Z", "price": 1.0}
        feed = mod.update_feed(row)
        assert feed["row_count"] == 1
        assert feed["last_row"] == row
        assert len(feed["rows"]) == 1

    def test_caps_at_500(self, setup_room):
        for i in range(510):
            mod.update_feed({"i": i})
        feed_data = json.loads(mod.FEED_PATH.read_text(encoding="utf-8"))
        assert len(feed_data["rows"]) == 500
        assert feed_data["row_count"] == 500
        # The last row should be i=509
        assert feed_data["rows"][-1]["i"] == 509

    def test_updates_row_count_and_last_row(self, setup_room):
        mod.update_feed({"price": 1.0})
        mod.update_feed({"price": 2.0})
        feed = mod.update_feed({"price": 3.0})
        assert feed["row_count"] == 3
        assert feed["last_row"]["price"] == 3.0


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND QUEUE (tmp_path)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateCommand:
    def test_creates_command_with_correct_fields(self, setup_room):
        # Create events file for append_event
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        assert cmd["command_id"].startswith("pocmd_")
        assert cmd["status"] == "queued"
        assert cmd["paper_only"] is True
        assert cmd["live_trading_forbidden"] is True
        assert cmd["action"] == "place_demo_trade"
        assert cmd["trade"]["symbol"] == "EURUSD_otc"
        assert cmd["trade"]["direction"] == "call"
        assert cmd["trade"]["amount"] == 10.0
        assert cmd["trade"]["duration"] == 60
        assert cmd["dispatched_utc"] is None
        assert cmd["result_utc"] is None
        assert cmd["result"] is None

    def test_appends_to_commands_list(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        mod.create_command("EURUSD_otc", "call", 10.0, 60)
        mod.create_command("GBPJPY_otc", "put", 20.0, 120)
        cmds = mod.read_commands()
        assert len(cmds["commands"]) == 2

    def test_caps_at_100(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        for i in range(105):
            mod.create_command("EURUSD_otc", "call", 1.0, 60)
        cmds = mod.read_commands()
        assert len(cmds["commands"]) == 100

    def test_writes_last_command(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        last = json.loads(mod.LAST_COMMAND_PATH.read_text(encoding="utf-8"))
        assert last["command_id"] == cmd["command_id"]

    def test_appends_event(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        mod.create_command("EURUSD_otc", "call", 10.0, 60)
        lines = mod.EVENTS_PATH.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        event = json.loads(lines[-1])
        assert event["payload"]["type"] == "bridge_command_created"


class TestNextPendingCommand:
    def test_returns_none_when_no_queued(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        result = mod.next_pending_command()
        assert result is None

    def test_dispatches_first_queued(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd1 = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        cmd2 = mod.create_command("GBPJPY_otc", "put", 20.0, 120)
        dispatched = mod.next_pending_command()
        assert dispatched is not None
        assert dispatched["command_id"] == cmd1["command_id"]
        assert dispatched["status"] == "dispatched"
        assert dispatched["dispatched_utc"] is not None

    def test_marks_as_dispatched(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        mod.create_command("EURUSD_otc", "call", 10.0, 60)
        dispatched = mod.next_pending_command()
        # Verify in persisted commands
        cmds = mod.read_commands()
        assert cmds["commands"][0]["status"] == "dispatched"

    def test_skips_already_dispatched(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd1 = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        cmd2 = mod.create_command("GBPJPY_otc", "put", 20.0, 120)
        mod.next_pending_command()  # dispatches cmd1
        dispatched2 = mod.next_pending_command()  # should dispatch cmd2
        assert dispatched2 is not None
        assert dispatched2["command_id"] == cmd2["command_id"]

    def test_returns_none_when_all_dispatched(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        mod.create_command("EURUSD_otc", "call", 10.0, 60)
        mod.next_pending_command()
        result = mod.next_pending_command()
        assert result is None


class TestCommandStatus:
    def test_returns_command_by_id(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        result = mod.command_status(cmd["command_id"])
        assert result is not None
        assert result["command_id"] == cmd["command_id"]

    def test_returns_none_for_unknown_id(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        result = mod.command_status("nonexistent_id")
        assert result is None


class TestRegisterCommandResult:
    def test_updates_existing_command_success(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        result = mod.register_command_result({
            "command_id": cmd["command_id"],
            "success": True,
            "trade_id": "t123",
        })
        assert result["status"] == "completed"
        assert result["result_utc"] is not None
        assert result["result"]["success"] is True

    def test_updates_existing_command_failure(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        result = mod.register_command_result({
            "command_id": cmd["command_id"],
            "success": False,
            "error": "timeout",
        })
        assert result["status"] == "failed"

    def test_creates_entry_for_unknown_command_id(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        result = mod.register_command_result({
            "command_id": "unknown_cmd_123",
            "success": True,
            "trade": {"symbol": "EURUSD_otc"},
        })
        assert result["command_id"] == "unknown_cmd_123"
        assert result["status"] == "completed"
        assert result["created_utc"] is None
        assert result["trade"]["symbol"] == "EURUSD_otc"

    def test_creates_failed_for_unknown_with_no_success(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        result = mod.register_command_result({
            "command_id": "unknown_cmd_456",
            "success": False,
        })
        assert result["status"] == "failed"

    def test_writes_last_result(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        mod.register_command_result({
            "command_id": cmd["command_id"],
            "success": True,
        })
        last = json.loads(mod.LAST_RESULT_PATH.read_text(encoding="utf-8"))
        assert last["command_id"] == cmd["command_id"]
        assert last["status"] == "completed"

    def test_appends_event(self, setup_room):
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        cmd = mod.create_command("EURUSD_otc", "call", 10.0, 60)
        mod.register_command_result({
            "command_id": cmd["command_id"],
            "success": True,
        })
        lines = mod.EVENTS_PATH.read_text(encoding="utf-8").strip().split("\n")
        last_event = json.loads(lines[-1])
        assert last_event["payload"]["type"] == "bridge_command_result"


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI ENDPOINTS (TestClient + monkeypatched paths)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_get_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_get_health_ok_true(self, client):
        data = client.get("/health").json()
        assert data["ok"] is True

    def test_get_health_correct_structure(self, client):
        data = client.get("/health").json()
        assert data["service"] == "pocketoption_bridge"
        assert data["mode"] == "paper_only"
        # Without seeded data, status is "stale" (no captured_utc)
        assert data["status"] in ("available", "stale")
        assert "bridge_port" in data
        assert "latest_pair" in data
        assert "latest_symbol" in data
        assert "demo_order_api_ready" in data
        assert "duration_candidates_count" in data
        assert "indicator_candidates_count" in data
        assert "indicator_readouts_count" in data

    def test_get_healthz_alias(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_health_with_latest_data(self, bridge_paths):
        """When latest.json has data, health reflects it."""
        from brain_v9.core.state_io import write_json
        mod.ensure_room_files()
        write_json(mod.LATEST_PATH, {
            "captured_utc": "2026-01-01T00:00:00Z",
            "current": {"pair": "EUR/USD OTC", "symbol": "EURUSD_otc"},
            "dom": {
                "duration_candidates": ["30s", "1m"],
                "indicator_candidates": ["RSI"],
                "indicator_readouts": [],
            },
            "ws": {
                "last_stream_symbol": "EURUSD_otc",
                "visible_symbol": "EUR/USD OTC",
                "stream_symbol_match": True,
            },
        })
        from fastapi.testclient import TestClient
        c = TestClient(mod.app)
        data = c.get("/health").json()
        assert data["latest_pair"] == "EUR/USD OTC"
        assert data["latest_symbol"] == "EURUSD_otc"
        assert data["duration_candidates_count"] == 2
        assert data["indicator_candidates_count"] == 1


class TestBalanceEndpoint:
    def test_get_balance_returns_200(self, client):
        resp = client.get("/balance")
        assert resp.status_code == 200

    def test_balance_structure(self, client):
        data = client.get("/balance").json()
        assert data["ok"] is True
        assert data["mode"] == "paper_only"
        assert data["currency"] == "USD"
        assert "balance" in data
        assert "balance_demo" in data

    def test_balance_with_data(self, bridge_paths):
        from brain_v9.core.state_io import write_json
        mod.ensure_room_files()
        write_json(mod.LATEST_PATH, {
            "captured_utc": "2026-01-01T00:00:00Z",
            "dom": {"balance_demo": 9876.54},
        })
        from fastapi.testclient import TestClient
        c = TestClient(mod.app)
        data = c.get("/balance").json()
        assert data["balance_demo"] == 9876.54
        assert data["balance"] == 9876.54


class TestNormalizedEndpoint:
    def test_get_normalized_returns_200(self, client):
        resp = client.get("/normalized")
        assert resp.status_code == 200

    def test_normalized_returns_feed(self, client):
        data = client.get("/normalized").json()
        assert "rows" in data
        assert "row_count" in data


class TestCsvEndpoint:
    def test_get_csv_returns_200(self, client):
        resp = client.get("/csv")
        assert resp.status_code == 200

    def test_csv_has_correct_headers(self, client):
        resp = client.get("/csv")
        text = resp.text
        first_line = text.strip().split("\n")[0]
        expected_headers = [
            "captured_utc", "pair", "symbol", "source_timestamp",
            "price", "payout_pct", "expiry_seconds", "socket_event_count",
            "last_socket_event", "last_socket_url", "balance_demo",
            "visible_price", "selected_duration_label",
            "duration_candidates_count", "indicator_candidates_count",
            "indicator_readouts_count",
        ]
        for h in expected_headers:
            assert h in first_line

    def test_csv_content_type(self, client):
        resp = client.get("/csv")
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_with_feed_data(self, bridge_paths):
        mod.ensure_room_files()
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        row = mod.build_row({"current": {"symbol": "EURUSD", "price": 1.123}})
        mod.update_feed(row)
        from fastapi.testclient import TestClient
        c = TestClient(mod.app)
        resp = c.get("/csv")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row


class TestTradesOpenEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/trades/open")
        assert resp.status_code == 200

    def test_returns_empty_trades(self, client):
        data = client.get("/trades/open").json()
        assert data["ok"] is True
        assert data["trades"] == []
        assert data["count"] == 0
        assert data["mode"] == "paper_only"


class TestTradesHistoryEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/trades/history")
        assert resp.status_code == 200

    def test_returns_rows_from_feed(self, bridge_paths):
        mod.ensure_room_files()
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        for i in range(5):
            mod.update_feed({"price": float(i)})
        from fastapi.testclient import TestClient
        c = TestClient(mod.app)
        data = c.get("/trades/history").json()
        assert data["ok"] is True
        assert data["count"] == 5

    def test_respects_limit_param(self, bridge_paths):
        mod.ensure_room_files()
        mod.EVENTS_PATH.write_text("", encoding="utf-8")
        for i in range(10):
            mod.update_feed({"price": float(i)})
        from fastapi.testclient import TestClient
        c = TestClient(mod.app)
        data = c.get("/trades/history?limit=3").json()
        assert data["count"] == 3
        # Should be last 3 rows
        assert data["trades"][-1]["price"] == 9.0


class TestTradeEndpoint:
    def test_post_trade_returns_200(self, client):
        resp = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
            "amount": 10,
            "duration": 60,
        })
        assert resp.status_code == 200

    def test_post_trade_creates_command(self, client):
        data = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
            "amount": 10,
            "duration": 60,
        }).json()
        assert data["success"] is True
        assert data["ok"] is True
        assert data["status"] == "queued"
        assert data["mode"] == "paper_only"
        assert data["paper_only"] is True
        assert data["live_trading_forbidden"] is True
        assert "command_id" in data
        assert "trade_id" in data
        assert data["command_id"] == data["trade_id"]
        assert data["command"]["trade"]["symbol"] == "EURUSD_otc"
        assert data["command"]["trade"]["direction"] == "call"

    def test_post_trade_default_amount_zero(self, client):
        data = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
        }).json()
        assert data["command"]["trade"]["amount"] == 0.0
        assert data["command"]["trade"]["duration"] == 0


class TestCommandsNextEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/commands/next")
        assert resp.status_code == 200

    def test_no_pending_returns_null_command(self, client):
        data = client.get("/commands/next").json()
        assert data["ok"] is True
        assert data["command"] is None

    def test_dispatches_queued_command(self, client):
        # Create a command via /trade first
        client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
            "amount": 10,
            "duration": 60,
        })
        data = client.get("/commands/next").json()
        assert data["command"] is not None
        assert data["command"]["status"] == "dispatched"


class TestCommandsStatusEndpoint:
    def test_returns_200_for_existing(self, client):
        trade_resp = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
            "amount": 10,
            "duration": 60,
        }).json()
        cmd_id = trade_resp["command_id"]
        resp = client.get(f"/commands/status/{cmd_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["command"]["command_id"] == cmd_id

    def test_returns_not_found_for_unknown(self, client):
        resp = client.get("/commands/status/nonexistent_id_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["command"] is None


class TestCommandsResultEndpoint:
    def test_registers_result(self, client):
        trade_resp = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
            "amount": 10,
            "duration": 60,
        }).json()
        cmd_id = trade_resp["command_id"]
        resp = client.post("/commands/result", json={
            "command_id": cmd_id,
            "success": True,
            "trade_id": "browser_t123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["command"]["status"] == "completed"

    def test_registers_failure(self, client):
        trade_resp = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "put",
            "amount": 5,
            "duration": 30,
        }).json()
        cmd_id = trade_resp["command_id"]
        data = client.post("/commands/result", json={
            "command_id": cmd_id,
            "success": False,
            "error": "element not found",
        }).json()
        assert data["command"]["status"] == "failed"


class TestCaptureEndpoint:
    def test_post_capture_returns_200(self, client):
        resp = client.post("/capture", json={
            "current": {"symbol": "EURUSD", "price": 1.1234},
        })
        assert resp.status_code == 200

    def test_post_capture_ingests_snapshot(self, client):
        data = client.post("/capture", json={
            "current": {"symbol": "EURUSD", "price": 1.1234},
        }).json()
        assert data["ok"] is True
        assert data["service"] == "pocketoption_bridge"
        assert data["mode"] == "paper_only"
        assert data["row_count"] >= 1
        assert "captured_utc" in data
        assert data["last_row"]["symbol"] == "EURUSD_otc"

    def test_capture_adds_captured_utc_if_missing(self, client):
        data = client.post("/capture", json={
            "current": {"symbol": "EURUSD", "price": 1.0},
        }).json()
        assert data["captured_utc"].endswith("Z")

    def test_capture_preserves_captured_utc(self, client):
        data = client.post("/capture", json={
            "captured_utc": "2026-06-15T12:00:00Z",
            "current": {"symbol": "EURUSD", "price": 1.0},
        }).json()
        assert data["captured_utc"] == "2026-06-15T12:00:00Z"

    def test_capture_writes_latest(self, bridge_paths, client):
        client.post("/capture", json={
            "captured_utc": "2026-06-15T12:00:00Z",
            "current": {"symbol": "TEST", "price": 9.99},
        })
        latest = json.loads(mod.LATEST_PATH.read_text(encoding="utf-8"))
        assert latest["captured_utc"] == "2026-06-15T12:00:00Z"

    def test_capture_updates_feed(self, bridge_paths, client):
        client.post("/capture", json={
            "current": {"symbol": "EURUSD", "price": 1.0},
        })
        client.post("/capture", json={
            "current": {"symbol": "EURUSD", "price": 2.0},
        })
        feed = json.loads(mod.FEED_PATH.read_text(encoding="utf-8"))
        assert feed["row_count"] == 2


class TestSnapshotAlias:
    def test_post_snapshot(self, client):
        resp = client.post("/snapshot", json={
            "current": {"symbol": "EURUSD", "price": 1.0},
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestBridgeSnapshotAlias:
    def test_post_bridge_snapshot(self, client):
        resp = client.post("/bridge/snapshot", json={
            "current": {"symbol": "EURUSD", "price": 1.0},
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestIngestAlias:
    def test_post_ingest(self, client):
        resp = client.post("/ingest", json={
            "current": {"symbol": "EURUSD", "price": 1.0},
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestRootAlias:
    def test_post_root(self, client):
        resp = client.post("/", json={
            "current": {"symbol": "EURUSD", "price": 1.0},
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestCaptureEdgeCases:
    def test_empty_payload(self, client):
        resp = client.post("/capture", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_non_dict_current(self, client):
        resp = client.post("/capture", json={
            "current": "not_a_dict",
            "symbol": "EURUSD",
        })
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullTradeLifecycle:
    def test_queue_dispatch_complete(self, client):
        """Full lifecycle: create trade → dispatch → register result."""
        # Step 1: Create trade
        trade = client.post("/trade", json={
            "symbol": "EURUSD_otc",
            "direction": "call",
            "amount": 10.0,
            "duration": 60,
        }).json()
        cmd_id = trade["command_id"]
        assert trade["status"] == "queued"

        # Step 2: Dispatch
        next_cmd = client.get("/commands/next").json()
        assert next_cmd["command"]["command_id"] == cmd_id
        assert next_cmd["command"]["status"] == "dispatched"

        # Step 3: Check status
        status = client.get(f"/commands/status/{cmd_id}").json()
        assert status["command"]["status"] == "dispatched"

        # Step 4: Register result
        result = client.post("/commands/result", json={
            "command_id": cmd_id,
            "success": True,
            "trade_id": "browser_123",
        }).json()
        assert result["command"]["status"] == "completed"

        # Step 5: Final status check
        final = client.get(f"/commands/status/{cmd_id}").json()
        assert final["command"]["status"] == "completed"

    def test_capture_then_health(self, client):
        """Capture a snapshot then verify health reflects data."""
        client.post("/capture", json={
            "captured_utc": "2026-03-26T10:00:00Z",
            "current": {"symbol": "GBPJPY", "pair": "GBP/JPY OTC", "price": 190.5},
            "dom": {
                "balance_demo": 5000.0,
                "duration_candidates": ["1m", "5m"],
                "indicator_candidates": ["RSI"],
                "indicator_readouts": [{"name": "RSI", "value": 70}],
            },
            "ws": {
                "last_stream_symbol": "GBPJPY_otc",
                "visible_symbol": "GBP/JPY OTC",
                "stream_symbol_match": True,
            },
        })
        health = client.get("/health").json()
        assert health["ok"] is True
        assert health["latest_pair"] == "GBP/JPY OTC"
        assert health["latest_symbol"] == "GBPJPY"
        assert health["duration_candidates_count"] == 2
        assert health["indicator_candidates_count"] == 1
        assert health["indicator_readouts_count"] == 1
