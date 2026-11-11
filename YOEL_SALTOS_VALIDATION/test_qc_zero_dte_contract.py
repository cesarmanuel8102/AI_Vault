from pathlib import Path
import json


PATH = Path(__file__).parent / "Yoel 0DTE First Rebound 20261025" / "main.py"


def source():
    return PATH.read_text(encoding="utf-8")


def test_cloud_config_exposes_entry_cutoff_parameter():
    config = json.loads((PATH.parent / "config.json").read_text(encoding="utf-8"))
    assert config["parameters"]["entry_cutoff_hour"] == "24"


def test_cloud_config_exposes_concentrated_daily_variant_parameters():
    config = json.loads((PATH.parent / "config.json").read_text(encoding="utf-8"))
    assert config["parameters"]["starting_cash"] == "100000"
    assert config["parameters"]["capital_fraction"] == "0.10"
    assert config["parameters"]["max_entries_per_day"] == "0"
    assert config["parameters"]["opening_signal_hour"] == "-1"
    assert config["parameters"]["failure_repeat"] == "false"
    assert config["parameters"]["adaptive_allocation"] == "false"


def test_frozen_dates_and_delta_dte_parameters_are_present():
    text = source()
    assert 'self.start_year = int(self.get_parameter("start_year") or 2025)' in text
    assert 'self.end_year = int(self.get_parameter("end_year") or 2026)' in text
    assert 'self.target_delta = float(self.get_parameter("target_delta") or 0.50)' in text
    assert 'self.target_dte = int(self.get_parameter("target_dte") or 0)' in text


def test_contract_selection_uses_expiry_and_live_delta():
    text = source()
    assert "select_expiry(" in text
    assert "select_contract_by_delta(" in text
    assert "contract_data.greeks.delta" in text
    assert "data.option_chains.values()" in text
    assert "candidate_limit" in text


def test_entry_uses_ten_percent_sizer_and_requires_fill_before_state():
    text = source()
    method = text.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    assert "contract_quantity(" in method
    assert method.index("OrderStatus.FILLED") < method.index("self.positions[ticker] =")


def test_optional_daily_variant_ranks_opening_signals_and_stops_after_first_fill():
    text = source()
    assert 'self.starting_cash = float(self.get_parameter("starting_cash") or 100000)' in text
    assert 'self.capital_fraction = float(self.get_parameter("capital_fraction") or 0.10)' in text
    assert 'self.max_entries_per_day = int(self.get_parameter("max_entries_per_day") or 0)' in text
    assert 'self.opening_signal_hour = int(self.get_parameter("opening_signal_hour") or -1)' in text
    assert "rank_daily_candidates(" in text
    assert "capital_fraction=self.capital_fraction" in text
    assert "self.daily_entry_counts[self.time.date()]" in text
    assert "contract_quantity_for_allocation(" in text
    assert "adaptive_allocation_fraction(" in text


def test_repeated_failure_monitor_keeps_checking_after_the_first_safe_checkpoint():
    text = source()
    assert 'self.failure_repeat = str(self.get_parameter("failure_repeat") or "false").lower() == "true"' in text
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert "if failure_checkpoint_due and failure_condition:" in manage
    assert "elif failure_checkpoint_due and not self.failure_repeat:" in manage


def test_optional_entry_cutoff_blocks_late_orders_without_changing_position_management():
    text = source()
    assert 'self.entry_cutoff_hour = int(self.get_parameter("entry_cutoff_hour") or 24)' in text
    entry = text.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    assert "entry_before_cutoff(self.time.hour, self.entry_cutoff_hour)" in entry
    assert entry.index("entry_before_cutoff(self.time.hour, self.entry_cutoff_hour)") < entry.index("self.market_order(")
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert "entry_before_cutoff" not in manage


def test_entry_rejects_contract_when_roundtrip_friction_exceeds_target():
    text = source()
    method = text.split("def _enter_ready_contracts", 1)[1].split("def _manage_positions", 1)[0]
    assert "friction_within_target(ask, self.entry_profit_hurdle)" in method
    assert "self.economics_skips += 1" in method
    assert method.index("friction_within_target(ask, self.entry_profit_hurdle)") < method.index("contract_quantity(")


def test_optional_trailing_replaces_fixed_target_and_tracks_peak_return():
    text = source()
    assert 'self.trailing_activation = float(self.get_parameter("trailing_activation") or 0)' in text
    assert 'self.trailing_distance = float(self.get_parameter("trailing_distance") or 0)' in text
    assert '"peak_pnl": 0.0' in text
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert 'position["peak_pnl"] = max(position["peak_pnl"], pnl)' in manage
    assert "trailing_profit_exit_due(" in manage
    assert 'self._close(ticker, "TRAILING_EXIT")' in manage
    assert 'not self.trailing_enabled and pnl >= self.take_profit' in manage


def test_optional_profit_ladder_scales_once_then_uses_runner_target():
    text = source()
    assert 'self.scale_out_fraction = float(self.get_parameter("scale_out_fraction") or 0)' in text
    assert 'self.runner_target = float(self.get_parameter("runner_target") or 0)' in text
    assert 'self.scale_out_trigger = float(self.get_parameter("scale_out_trigger") or 0)' in text
    assert '"scaled_out": False' in text
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert 'not position["scaled_out"] and pnl >= self.scale_out_trigger' in manage
    assert "self._scale_out(ticker)" in manage
    assert 'not position["scaled_out"] and not self.trailing_enabled and pnl >= self.take_profit' in manage
    assert 'position["scaled_out"] and self.runner_target > 0 and pnl >= self.runner_target' in manage
    assert 'self._close(ticker, "RUNNER_TARGET")' in manage
    scale = text.split("def _scale_out", 1)[1].split("def _close", 1)[0]
    assert "scale_out_quantity(" in scale
    assert 'position["scaled_out"] = True' in scale


def test_trailing_economics_gate_uses_initial_protected_profit():
    text = source()
    assert "self.entry_profit_hurdle =" in text
    assert "self.trailing_activation - self.trailing_distance" in text
    method = text.split("def _enter_ready_contracts", 1)[1].split("def _manage_positions", 1)[0]
    assert "friction_within_target(ask, self.entry_profit_hurdle)" in method


def test_entry_records_effective_delta_and_dte():
    text = source()
    assert '"entry_delta"' in text
    assert '"entry_dte"' in text
    assert 'self.set_runtime_statistic("Average Entry Delta"' in text
    assert 'self.set_runtime_statistic("Average Entry DTE"' in text


def test_lifecycle_has_35_percent_target_no_stop_and_1555_exit():
    text = source()
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert 'self.take_profit = float(self.get_parameter("take_profit") or 0.35)' in text
    assert "pnl >= self.take_profit" in manage
    assert "stop" not in manage.lower()
    assert 'before_market_close("SPY", 5)' in text
    assert "def _close_all" in text


def test_optional_max_hold_minutes_is_measured_from_actual_entry_time():
    text = source()
    assert 'self.max_hold_minutes = int(self.get_parameter("max_hold_minutes") or 0)' in text
    entry = text.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert '"entry_time": self.time' in entry
    assert "self.time - position[\"entry_time\"]" in manage
    assert "timedelta(minutes=self.max_hold_minutes)" in manage


def test_train_and_validation_years_are_parameters_with_frozen_2026_cutoff():
    text = source()
    assert 'self.start_year = int(self.get_parameter("start_year") or 2025)' in text
    assert 'self.end_year = int(self.get_parameter("end_year") or 2026)' in text
    assert "self.set_start_date(self.start_year, 1, 1)" in text
    assert "(10, 25) if self.end_year == 2026 else (12, 31)" in text


def test_failure_to_launch_uses_actual_fill_time_after_take_profit():
    text = source()
    assert 'self.failure_minutes = int(self.get_parameter("failure_minutes") or 0)' in text
    assert 'self.failure_min_pnl = float(self.get_parameter("failure_min_pnl") or 0)' in text
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert "failure_to_launch_due(" in manage
    assert "position[\"entry_time\"]" in manage
    assert manage.index("pnl >= self.take_profit") < manage.index("failure_to_launch_due(")
    assert 'self._close(ticker, "FAILURE_EXIT")' in manage


def test_failure_exit_can_require_adverse_directional_underlying_return():
    text = source()
    assert 'self.failure_underlying_adverse = str(self.get_parameter("failure_underlying_adverse") or "false").lower() == "true"' in text
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert "adverse_failure_to_launch_due(" in manage
    assert 'position["direction"] * (underlying_now / position["underlying_entry"] - 1)' in manage
    assert manage.index("pnl >= self.take_profit") < manage.index("adverse_failure_to_launch_due(")
    assert '"failure_checked": False' in text
    assert 'not position["failure_checked"]' in manage
    assert 'position["failure_checked"] = True' in manage


def test_quality_filter_is_optional_and_records_signal_features():
    text = source()
    assert 'self.quality_filter = str(self.get_parameter("quality_filter") or "false").lower() == "true"' in text
    hourly = text.split("def _on_hourly", 1)[1].split("def on_data", 1)[0]
    assert "quality_signal(" in hourly
    assert '"relative_volume": relative_volume' in hourly
    assert '"close_location": close_location' in hourly
    assert "self.quality_skips += 1" in hourly
    assert "FAILURE_EXIT" in text
    assert 'self.set_runtime_statistic("Failure Exits"' in text


def test_trace_mode_records_entry_context_and_open_position_checkpoints_without_exits():
    text = source()
    assert 'self.trace_mode = str(self.get_parameter("trace_mode") or "false").lower() == "true"' in text
    assert "self.trace_checkpoints = (3, 5, 10, 15, 30)" in text
    hourly = text.split("def _on_hourly", 1)[1].split("def on_data", 1)[0]
    assert '"level_price": float(levels[period])' in hourly
    assert '"signal_low": float(bar.low)' in hourly
    assert '"signal_high": float(bar.high)' in hourly
    entry = text.split("def _enter_ready_contracts", 1)[1].split("def _manage_positions", 1)[0]
    assert '"underlying_entry": float(self.securities[context["underlying"]].price)' in entry
    assert '"traced_checkpoints": set()' in entry
    manage = text.split("def _manage_positions", 1)[1].split("def _close", 1)[0]
    assert "self._trace_position(ticker, position, bid)" in manage
    trace = text.split("def _trace_position", 1)[1].split("def _scale_out", 1)[0]
    assert "checkpoint_snapshot(" in trace
    assert 'self.debug("TRACE|" + json.dumps(record, separators=(",", ":")))' in trace
    assert "_close(" not in trace


def test_causal_selector_collects_pre_entry_features_and_runs_before_sizing():
    text = source()
    assert 'self.causal_selector = str(self.get_parameter("causal_selector") or "false").lower() == "true"' in text
    hourly = text.split("def _on_hourly", 1)[1].split("def on_data", 1)[0]
    for field in ("body_strength", "range_atr", "level_rejection_atr"):
        assert f'"{field}":' in hourly

    entry = text.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    assert "passes_causal_quality_gate(" in entry
    assert "rank_daily_candidates(" in entry
    assert "rank_quality_candidates(" not in entry
    selector_index = entry.index("passes_causal_quality_gate(")
    assert selector_index < entry.index("contract_quantity_for_allocation(")
    assert selector_index < entry.index("contract_quantity(")
    for field in ("body_strength", "range_atr", "level_rejection_atr"):
        assert f'"{field}": round(context["{field}"]' in entry


def test_causal_selector_never_passes_capital_fields_to_quality_functions():
    text = source()
    entry = text.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    gate_call = entry.split("passes_causal_quality_gate(", 1)[1].split(")", 1)[0]
    for forbidden in ("portfolio.cash", "total_portfolio_value", "quantity"):
        assert forbidden not in gate_call
    ranking_block = entry.split("ranking_candidates =", 1)[1].split(
        "for candidate_index", 1
    )[0]
    for forbidden in ("portfolio.cash", "total_portfolio_value", "quantity"):
        assert forbidden not in ranking_block
