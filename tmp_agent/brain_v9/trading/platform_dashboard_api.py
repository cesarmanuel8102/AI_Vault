"""
Brain V9 - Platform Dashboard API
Dashboard de plataformas reanclado al estado canónico del strategy engine.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from math import sqrt, tanh
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.autonomy.platform_accumulators import Platform, get_multi_platform_accumulator
from brain_v9.trading.platform_manager import get_platform_manager  # compatibility for tests/patching
from brain_v9.config import (
    BASE_PATH,
    FEATURE_MAX_AGE_SECONDS,
    IBKR_PROBE_ARTIFACT,
    PO_BRIDGE_LATEST_ARTIFACT,
    PO_COMMAND_RESULT_ARTIFACT,
)
from brain_v9.core.state_io import read_json

log = logging.getLogger("platform_dashboard_api")

def _state_path() -> Path:
    return BASE_PATH / "tmp_agent" / "state"


def _strategy_engine_path() -> Path:
    return _state_path() / "strategy_engine"


def _ledger_path() -> Path:
    return _strategy_engine_path() / "signal_paper_execution_ledger.json"


def _scorecards_path() -> Path:
    return _strategy_engine_path() / "strategy_scorecards.json"


def _signals_path() -> Path:
    return _strategy_engine_path() / "strategy_signal_snapshot_latest.json"


def _features_path() -> Path:
    return _strategy_engine_path() / "market_feature_snapshot_latest.json"


def _ranking_path() -> Path:
    return _strategy_engine_path() / "strategy_ranking_v2_latest.json"


def _platforms_state_path() -> Path:
    return _state_path() / "platforms"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        log.debug("Could not parse timestamp %r: %s", value, exc)
        return None


def _age_seconds(value: Any) -> float | None:
    ts = _parse_utc(value)
    if not ts:
        return None
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())


def _round(value: Any, digits: int = 4) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class PlatformDashboardAPI:
    """API para dashboard de plataformas separadas basada en artifacts vivos."""

    _VENUE_MAP: Dict[str, str] = {
        "pocket_option": "pocket_option",
        "ibkr": "ibkr",
        "internal_paper": "internal",
    }

    def __init__(self):
        self.accumulators = get_multi_platform_accumulator()
        self._ibkr_live_cache: Dict[str, Any] | None = None
        self._ibkr_live_cache_utc: float = 0.0

    def _read_scorecards(self) -> Dict[str, Dict[str, Any]]:
        payload = read_json(_scorecards_path(), {})
        scorecards = payload.get("scorecards", {}) if isinstance(payload, dict) else {}
        return scorecards if isinstance(scorecards, dict) else {}

    def _read_ledger_entries(self) -> List[Dict[str, Any]]:
        payload = read_json(_ledger_path(), {})
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        return entries if isinstance(entries, list) else []

    def _read_signal_items(self) -> List[Dict[str, Any]]:
        payload = read_json(_signals_path(), {})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return items if isinstance(items, list) else []

    def _read_feature_items(self) -> List[Dict[str, Any]]:
        payload = read_json(_features_path(), {})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return items if isinstance(items, list) else []

    def _read_ranked_candidates(self) -> List[Dict[str, Any]]:
        payload = read_json(_ranking_path(), {})
        items = payload.get("ranked", []) if isinstance(payload, dict) else []
        return items if isinstance(items, list) else []

    def _read_platform_u_history(self, platform_name: str) -> Dict[str, Any]:
        path = _platforms_state_path() / f"{platform_name}_u.json"
        payload = read_json(path, {})
        return payload if isinstance(payload, dict) else {}

    def _read_platform_metrics_state(self, platform_name: str) -> Dict[str, Any]:
        path = _platforms_state_path() / f"{platform_name}_metrics.json"
        payload = read_json(path, {})
        return payload if isinstance(payload, dict) else {}

    def _platform_entries(self, platform_name: str) -> List[Dict[str, Any]]:
        venue = self._VENUE_MAP.get(platform_name, platform_name)
        return [e for e in self._read_ledger_entries() if e.get("venue") == venue]

    def _platform_scorecards(self, platform_name: str) -> List[Dict[str, Any]]:
        venue = self._VENUE_MAP.get(platform_name, platform_name)
        return [c for c in self._read_scorecards().values() if isinstance(c, dict) and c.get("venue") == venue]

    def _platform_signals(self, platform_name: str) -> List[Dict[str, Any]]:
        venue = self._VENUE_MAP.get(platform_name, platform_name)
        return [s for s in self._read_signal_items() if s.get("venue") == venue]

    def _platform_features(self, platform_name: str) -> List[Dict[str, Any]]:
        venue = self._VENUE_MAP.get(platform_name, platform_name)
        return [f for f in self._read_feature_items() if f.get("venue") == venue]

    def _platform_ranked_candidates(self, platform_name: str) -> List[Dict[str, Any]]:
        venue = self._VENUE_MAP.get(platform_name, platform_name)
        return [c for c in self._read_ranked_candidates() if c.get("venue") == venue]

    def _platform_ready_signals_now(self, platform_name: str) -> int:
        return sum(1 for c in self._platform_ranked_candidates(platform_name) if c.get("execution_ready_now"))

    def _platform_probation_signals(self, platform_name: str) -> int:
        return sum(1 for c in self._platform_ranked_candidates(platform_name) if c.get("probation_eligible"))

    def _platform_validated_signals(self, platform_name: str) -> int:
        return sum(
            1 for c in self._platform_ranked_candidates(platform_name)
            if c.get("execution_ready_now") and c.get("edge_state") in {"validated", "promotable"}
        )

    def _latest_platform_entry(self, platform_name: str) -> Dict[str, Any] | None:
        entries = self._platform_entries(platform_name)
        if not entries:
            return None
        ordered = list(enumerate(entries))
        ordered.sort(
            key=lambda item: (
                str(item[1].get("resolved_utc") or item[1].get("timestamp") or ""),
                item[0],
            ),
            reverse=True,
        )
        return ordered[0][1]

    def _platform_accumulator(self, platform_name: str) -> Dict[str, Any]:
        try:
            platform_enum = Platform(platform_name)
            return self.accumulators.get_platform_status(platform_enum)
        except Exception as exc:
            log.debug("Accumulator status unavailable for %s: %s", platform_name, exc)
            return {}

    def _read_ibkr_live_snapshot(self) -> Dict[str, Any]:
        now = time.time()
        if self._ibkr_live_cache and (now - self._ibkr_live_cache_utc) < 60:
            return dict(self._ibkr_live_cache)

        snapshot: Dict[str, Any] = {
            "connected": False,
            "managed_accounts": [],
            "positions_count": 0,
            "open_trades_count": 0,
            "positions": [],
            "checked_utc": _utc_now_iso(),
            "source": "ibkr_readonly_probe",
            "error": None,
        }
        try:
            client_id = 900  # Fixed ID — avoids polluting Gateway with dozens of client entries
            script = f"""
import json
from ib_insync import IB
ib = IB()
payload = {{"connected": False, "managed_accounts": [], "positions_count": 0, "open_trades_count": 0, "positions": []}}
try:
    ib.connect("127.0.0.1", 4002, clientId={client_id}, timeout=5)
    payload["connected"] = ib.isConnected()
    payload["managed_accounts"] = list(ib.managedAccounts() or [])
    positions = ib.positions() or []
    payload["positions_count"] = len(positions)
    payload["open_trades_count"] = len(ib.openTrades() or [])
    payload["positions"] = [{{
        "account": p.account,
        "symbol": getattr(p.contract, "symbol", None),
        "secType": getattr(p.contract, "secType", None),
        "position": p.position,
        "avgCost": p.avgCost,
    }} for p in positions[:20]]
except Exception as exc:
    payload["error"] = str(exc)
finally:
    try:
        ib.disconnect()
    except Exception:
        pass
print(json.dumps(payload))
"""
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            stdout = (proc.stdout or "").strip()
            if proc.returncode == 0 and stdout:
                payload = json.loads(stdout)
                snapshot.update({
                    "connected": bool(payload.get("connected")),
                    "managed_accounts": list(payload.get("managed_accounts") or []),
                    "positions_count": _safe_int(payload.get("positions_count")),
                    "open_trades_count": _safe_int(payload.get("open_trades_count")),
                    "positions": payload.get("positions") or [],
                    "error": payload.get("error"),
                })
            else:
                snapshot["error"] = (proc.stderr or stdout or f"subprocess_failed:{proc.returncode}").strip()
        except Exception as exc:
            snapshot["error"] = str(exc)

        self._ibkr_live_cache = snapshot
        self._ibkr_live_cache_utc = now
        return dict(snapshot)

    def _compute_live_metrics(self, platform_name: str) -> Dict[str, Any]:
        scorecards = self._platform_scorecards(platform_name)
        entries = self._platform_entries(platform_name)
        resolved = [e for e in entries if bool(e.get("resolved"))]

        total_trades = sum(_safe_int(card.get("entries_resolved")) for card in scorecards)
        wins = sum(_safe_int(card.get("wins")) for card in scorecards)
        losses = sum(_safe_int(card.get("losses")) for card in scorecards)
        total_profit = sum(_safe_float(card.get("net_pnl")) for card in scorecards)
        win_rate = (wins / total_trades) if total_trades else 0.0
        expectancy = (total_profit / total_trades) if total_trades else 0.0
        sample_quality = min(total_trades / 20.0, 1.0)

        # Canonical totals come from strategy scorecards. The ledger is used
        # only for chronology-sensitive approximations such as drawdown/recency.
        profits = [_safe_float(e.get("profit")) for e in resolved]

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for profit in profits:
            equity += profit
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)

        sharpe_ratio = 0.0
        if len(profits) >= 2:
            mean = total_profit / len(profits)
            variance = sum((p - mean) ** 2 for p in profits) / len(profits)
            std = sqrt(variance)
            if std > 0:
                sharpe_ratio = mean / std

        last_trade_time = None
        if entries:
            last_trade_time = max((e.get("resolved_utc") or e.get("timestamp")) for e in entries)

        return {
            "total_trades": total_trades,
            "winning_trades": wins,
            "losing_trades": losses,
            "win_rate": win_rate,
            "total_profit": total_profit,
            "expectancy": expectancy,
            "sample_quality": sample_quality,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "last_trade_time": last_trade_time,
            "ledger_resolved_trades": len(resolved),
        }

    def _compute_live_u(self, metrics: Dict[str, Any]) -> float:
        total_trades = _safe_int(metrics.get("total_trades"))
        if total_trades < 5:
            return 0.0
        expectancy = _safe_float(metrics.get("expectancy"))
        growth_signal = max(-1.0, min(1.0, tanh(expectancy / 3.0)))
        total_profit = _safe_float(metrics.get("total_profit"))
        peak_profit = max(total_profit, 1.0)
        drawdown_fraction = _safe_float(metrics.get("max_drawdown")) / peak_profit
        drawdown_penalty = max(0.0, min(2.0, drawdown_fraction / 0.30))
        return _round(growth_signal - drawdown_penalty)

    def _compute_stored_metrics_u(self, stored_metrics: Dict[str, Any]) -> float | None:
        total_trades = _safe_int(stored_metrics.get("total_trades"))
        if total_trades < 5:
            return None
        expectancy = _safe_float(stored_metrics.get("expectancy"))
        growth_signal = max(-1.0, min(1.0, tanh(expectancy / 3.0)))
        peak_profit = max(_safe_float(stored_metrics.get("peak_profit")), 1.0)
        drawdown_fraction = _safe_float(stored_metrics.get("max_drawdown")) / peak_profit
        drawdown_penalty = max(0.0, min(2.0, drawdown_fraction / 0.30))
        tail_risk_penalty = max(0.0, min(2.0, _safe_float(stored_metrics.get("largest_loss_streak")) / 5.0))
        return _round(growth_signal - drawdown_penalty - tail_risk_penalty)

    def _platform_status(self, platform_name: str) -> Dict[str, Any]:
        signals = self._platform_signals(platform_name)
        features = self._platform_features(platform_name)

        if platform_name == "pocket_option":
            bridge = read_json(PO_BRIDGE_LATEST_ARTIFACT, {})
            command_result = read_json(PO_COMMAND_RESULT_ARTIFACT, {})
            result_payload = command_result.get("result") if isinstance(command_result.get("result"), dict) else {}
            captured_utc = bridge.get("captured_utc") if isinstance(bridge, dict) else None
            age = _age_seconds(captured_utc)
            feature = features[0] if features else {}
            is_fresh = bool(feature.get("price_available")) and not bool(feature.get("is_stale"))
            return {
                "status": "active" if is_fresh else "degraded" if captured_utc else "idle",
                "detail": "demo_bridge_live" if is_fresh else "bridge_stale_or_missing",
                "captured_utc": captured_utc,
                "data_age_seconds": round(age, 3) if age is not None else None,
                "ready_signals": self._platform_ready_signals_now(platform_name),
                "validated_ready_signals": self._platform_validated_signals(platform_name),
                "probation_ready_signals": self._platform_probation_signals(platform_name),
                "last_browser_command_utc": command_result.get("result_utc") or command_result.get("dispatched_utc"),
                "last_browser_command_status": (result_payload.get("status") or command_result.get("status")),
                "last_browser_command_symbol": ((result_payload.get("trade") or {}).get("symbol") or ((command_result.get("trade") or {}).get("symbol"))),
                "last_browser_command_click_submitted": bool(result_payload.get("accepted_click")),
                "last_browser_command_confirmed": bool(result_payload.get("ui_trade_confirmed")),
            }

        if platform_name == "ibkr":
            probe = read_json(IBKR_PROBE_ARTIFACT, {})
            live = self._read_ibkr_live_snapshot()
            checked_utc = probe.get("checked_utc") if isinstance(probe, dict) else None
            connected = bool(live.get("connected")) or bool(probe.get("connected"))
            age = _age_seconds(live.get("checked_utc") or checked_utc)
            probe_accounts = probe.get("managed_accounts") if isinstance(probe, dict) else []
            if isinstance(probe_accounts, str):
                probe_accounts = [probe_accounts] if probe_accounts else []
            return {
                "status": "active" if connected else "degraded" if checked_utc else "idle",
                "detail": "marketdata_live" if connected else "marketdata_disconnected",
                "captured_utc": live.get("checked_utc") or checked_utc,
                "data_age_seconds": round(age, 3) if age is not None else None,
                "ready_signals": self._platform_ready_signals_now(platform_name),
                "validated_ready_signals": self._platform_validated_signals(platform_name),
                "probation_ready_signals": self._platform_probation_signals(platform_name),
                "managed_accounts": live.get("managed_accounts") or probe_accounts or [],
                "positions_count": _safe_int(live.get("positions_count")),
                "open_trades_count": _safe_int(live.get("open_trades_count")),
                "positions": live.get("positions") or [],
                "probe_connected": bool(probe.get("connected")),
                "live_connected": bool(live.get("connected")),
                "live_error": live.get("error"),
            }

        return {
            "status": "idle",
            "detail": "no_live_connector",
            "captured_utc": None,
            "data_age_seconds": None,
            "ready_signals": self._platform_ready_signals_now(platform_name),
            "validated_ready_signals": self._platform_validated_signals(platform_name),
            "probation_ready_signals": self._platform_probation_signals(platform_name),
        }

    def _platform_is_unused(self, platform_name: str, metrics: Dict[str, Any], stored_metrics: Dict[str, Any], status: Dict[str, Any]) -> bool:
        if platform_name != "internal_paper":
            return False
        return (
            _safe_int(metrics.get("total_trades")) == 0
            and _safe_int(stored_metrics.get("total_trades")) == 0
            and str(status.get("status") or "idle") == "idle"
        )

    def _live_u_payload(self, platform_name: str, metrics: Dict[str, Any], status: Dict[str, Any], stored_metrics: Dict[str, Any]) -> Dict[str, Any]:
        history_payload = self._read_platform_u_history(platform_name)
        if self._platform_is_unused(platform_name, metrics, stored_metrics, status):
            return {
                "current": None,
                "verdict": "inactive",
                "blockers": ["platform_not_in_use"],
                "trend_24h": "inactive",
                "history_count": 0,
                "runtime_current": None,
                "performance_current": None,
                "display_basis": "inactive",
            }
        stored_u = history_payload.get("u_proxy")
        runtime_u = _safe_float(stored_u) if stored_u is not None else self._compute_live_u(metrics)
        performance_u = self._compute_stored_metrics_u(stored_metrics)
        live_positions = _safe_int(status.get("positions_count"))
        live_open_trades = _safe_int(status.get("open_trades_count"))
        blockers: List[str] = []
        if _safe_int(metrics.get("total_trades")) < 5:
            blockers.append("insufficient_resolved_sample")
        if _safe_float(metrics.get("sample_quality")) < 0.3:
            blockers.append("sample_not_ready")
        if status.get("status") == "degraded":
            blockers.append("connector_degraded")
        if status.get("status") == "idle":
            blockers.append("no_live_data")
        if runtime_u <= 0:
            blockers.append("u_proxy_non_positive")
        if performance_u is not None and performance_u <= 0:
            blockers.append("performance_u_non_positive")
        if platform_name == "ibkr" and (live_positions > 0 or live_open_trades > 0) and performance_u is None:
            blockers.append("live_positions_present_without_resolved_sample")

        if history_payload.get("blockers"):
            blockers.extend([str(b) for b in history_payload.get("blockers", []) if b])
        blockers = list(dict.fromkeys(blockers))

        if performance_u is not None:
            display_u = performance_u
            display_basis = "lifetime_performance"
        elif platform_name == "ibkr" and (live_positions > 0 or live_open_trades > 0):
            display_u = None
            display_basis = "live_positions_no_resolved_sample"
        else:
            display_u = runtime_u
            display_basis = "runtime_skip_guardrail"

        if history_payload.get("verdict") and display_basis == "runtime_skip_guardrail":
            verdict = str(history_payload.get("verdict"))
        elif display_u is None and platform_name == "ibkr" and (live_positions > 0 or live_open_trades > 0):
            verdict = "monitoring_live_positions"
        elif (display_u or 0.0) > 0.3:
            verdict = "ready_for_promotion"
        elif (display_u or 0.0) > 0:
            verdict = "needs_improvement"
        else:
            verdict = "no_promote"

        return {
            "current": _round(display_u) if display_u is not None else None,
            "verdict": verdict,
            "blockers": blockers,
            "trend_24h": history_payload.get("trend_24h", "stable"),
            "history_count": len(history_payload.get("history", [])) if isinstance(history_payload.get("history"), list) else 0,
            "runtime_current": _round(runtime_u),
            "performance_current": _round(performance_u) if performance_u is not None else None,
            "display_basis": display_basis,
        }

    def _reference_metrics_payload(self, metrics: Dict[str, Any], stored_metrics: Dict[str, Any], u_score: Dict[str, Any]) -> Dict[str, Any]:
        display_basis = str(u_score.get("display_basis") or "runtime_skip_guardrail")
        resolved_win_rate = round(metrics["win_rate"] * 100, 2) if _safe_int(metrics.get("total_trades")) > 0 else None
        lifetime_win_rate_raw = _optional_float(stored_metrics.get("win_rate"))
        if lifetime_win_rate_raw is not None and lifetime_win_rate_raw <= 1.0:
            lifetime_win_rate = lifetime_win_rate_raw * 100.0
        else:
            lifetime_win_rate = lifetime_win_rate_raw

        if display_basis == "lifetime_performance":
            return {
                "reference_basis": "lifetime_performance",
                "reference_basis_label": "lifetime platform performance",
                "reference_trades": _safe_int(stored_metrics.get("total_trades")),
                "reference_win_rate": _round(lifetime_win_rate, 2) if lifetime_win_rate is not None else None,
                "reference_profit": _round(_optional_float(stored_metrics.get("total_profit"))),
            }

        if display_basis == "inactive":
            return {
                "reference_basis": "inactive",
                "reference_basis_label": "inactive platform",
                "reference_trades": None,
                "reference_win_rate": None,
                "reference_profit": None,
            }

        if display_basis == "live_positions_no_resolved_sample":
            return {
                "reference_basis": "live_positions_no_resolved_sample",
                "reference_basis_label": "live broker positions without resolved sample",
                "reference_trades": None,
                "reference_win_rate": None,
                "reference_profit": None,
            }

        return {
            "reference_basis": "resolved_sample",
            "reference_basis_label": "resolved sample",
            "reference_trades": _safe_int(metrics.get("total_trades")),
            "reference_win_rate": _round(resolved_win_rate, 2) if resolved_win_rate is not None else None,
            "reference_profit": _round(_optional_float(metrics.get("total_profit"))),
        }

    def get_platform_summary(self, platform_name: str) -> Dict[str, Any]:
        metrics = self._compute_live_metrics(platform_name)
        stored_metrics = self._read_platform_metrics_state(platform_name)
        status = self._platform_status(platform_name)
        acc_status = self._platform_accumulator(platform_name)
        u_score = self._live_u_payload(platform_name, metrics, status, stored_metrics)
        reference_metrics = self._reference_metrics_payload(metrics, stored_metrics, u_score)
        latest_entry = self._latest_platform_entry(platform_name) or {}
        scorecards = self._platform_scorecards(platform_name)
        entries_open = sum(_safe_int(card.get("entries_open")) for card in scorecards)

        execution_type = "none"
        if latest_entry:
            if latest_entry.get("venue") == "pocket_option":
                if latest_entry.get("browser_trade_confirmed"):
                    execution_type = "browser_ui_confirmed"
                elif latest_entry.get("browser_command_dispatched"):
                    execution_type = "browser_click_unverified"
                elif latest_entry.get("paper_shadow"):
                    execution_type = "paper_shadow_only"
            elif latest_entry.get("paper_shadow"):
                execution_type = "paper_shadow"

        if latest_entry.get("executor_platform"):
            execution_type = f"{execution_type}:{latest_entry.get('executor_platform')}"

        return {
            "platform": platform_name,
            "timestamp": _utc_now_iso(),
            "u_score": u_score,
            "metrics": {
                "total_trades": metrics["total_trades"],
                "entries_open": entries_open,
                "winning_trades": metrics["winning_trades"],
                "losing_trades": metrics["losing_trades"],
                "win_rate": round(metrics["win_rate"] * 100, 2) if metrics["total_trades"] > 0 else 0.0,
                "total_profit": _round(metrics["total_profit"]),
                "expectancy": _round(metrics["expectancy"]),
                "sample_quality": _round(metrics["sample_quality"]),
                "max_drawdown": _round(metrics["max_drawdown"]),
                "sharpe_ratio": _round(metrics["sharpe_ratio"]),
                "last_trade_time": metrics.get("last_trade_time"),
                "lifetime_total_trades": _safe_int(stored_metrics.get("total_trades")),
                "lifetime_total_profit": _safe_float(stored_metrics.get("total_profit")),
                "lifetime_win_rate": _safe_float(stored_metrics.get("win_rate")) * 100.0 if _safe_float(stored_metrics.get("win_rate")) <= 1.0 else _safe_float(stored_metrics.get("win_rate")),
                "reference_basis": reference_metrics.get("reference_basis"),
                "reference_basis_label": reference_metrics.get("reference_basis_label"),
                "reference_total_trades": reference_metrics.get("reference_trades"),
                "reference_total_profit": reference_metrics.get("reference_profit"),
                "reference_win_rate": reference_metrics.get("reference_win_rate"),
            },
            "accumulator": {
                "running": acc_status.get("running", False),
                "session_trades": acc_status.get("session_trades", 0),
                "consecutive_skips": acc_status.get("consecutive_skips", 0),
                "last_trade": acc_status.get("last_trade"),
            },
            "execution": {
                "last_trade_time": metrics.get("last_trade_time"),
                "last_browser_command_utc": status.get("last_browser_command_utc"),
                "last_browser_command_status": status.get("last_browser_command_status"),
                "last_browser_command_symbol": status.get("last_browser_command_symbol"),
                "last_browser_command_click_submitted": status.get("last_browser_command_click_submitted"),
                "last_browser_command_confirmed": status.get("last_browser_command_confirmed"),
                "last_executor_platform": latest_entry.get("executor_platform"),
                "last_execution_type": execution_type,
                "last_trade_paper_shadow": bool(latest_entry.get("paper_shadow")) if latest_entry else False,
                "live_positions_count": status.get("positions_count"),
                "live_open_trades_count": status.get("open_trades_count"),
                "live_positions": status.get("positions", []),
                "managed_accounts": status.get("managed_accounts", []),
                "probe_connected": status.get("probe_connected"),
                "live_connected": status.get("live_connected"),
                "live_error": status.get("live_error"),
            },
            "status": status["status"],
            "detail": status["detail"],
            "data_age_seconds": status["data_age_seconds"],
            "ready_signals": status["ready_signals"],
            "validated_ready_signals": status.get("validated_ready_signals", 0),
            "probation_ready_signals": status.get("probation_ready_signals", 0),
        }

    def get_all_platforms_summary(self) -> Dict[str, Any]:
        platforms = ["pocket_option", "ibkr", "internal_paper"]
        platforms_data = {platform: self.get_platform_summary(platform) for platform in platforms}
        return {
            "generated_utc": _utc_now_iso(),
            "platforms": platforms_data,
            "comparison": self.compare_platforms(),
            "recommendations": self._generate_recommendations(platforms_data),
        }

    def _generate_recommendations(self, platforms_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []
        for platform, data in platforms_data.items():
            u_score = _safe_float(data.get("u_score", {}).get("current"))
            status = str(data.get("status") or "idle")
            trades = _safe_int(data.get("metrics", {}).get("total_trades"))
            ready_signals = _safe_int(data.get("ready_signals"))
            validated_ready = _safe_int(data.get("validated_ready_signals"))
            probation_ready = _safe_int(data.get("probation_ready_signals"))

            if status == "degraded":
                recommendations.append({
                    "platform": platform,
                    "priority": "high",
                    "action": "repair_connector",
                    "reason": f"{platform} tiene conector degradado. Restaurar feed antes de seguir acumulando muestra.",
                })
            elif validated_ready > 0:
                recommendations.append({
                    "platform": platform,
                    "priority": "medium",
                    "action": "exploit_validated_edge",
                    "reason": f"{platform} ya tiene señales listas con edge validado; priorizar ejecución disciplinada sobre exploración adicional.",
                })
            elif ready_signals > 0 and ready_signals == probation_ready:
                recommendations.append({
                    "platform": platform,
                    "priority": "medium",
                    "action": "run_probation_carefully",
                    "reason": f"{platform} solo tiene señales en probation; conviene usarlas como exploración controlada, no como edge confirmado.",
                })
            elif ready_signals > 0 and trades < 5:
                recommendations.append({
                    "platform": platform,
                    "priority": "medium",
                    "action": "increase_resolved_sample",
                    "reason": f"{platform} tiene señales listas pero muestra insuficiente ({trades} trades resueltos).",
                })
            elif u_score < 0 and trades > 0:
                recommendations.append({
                    "platform": platform,
                    "priority": "medium",
                    "action": "review_strategy",
                    "reason": f"{platform} acumula pérdidas según los scorecards canónicos del strategy engine.",
                })
            elif status == "idle":
                recommendations.append({
                    "platform": platform,
                    "priority": "low",
                    "action": "wait_or_seed",
                    "reason": f"{platform} no tiene feed ni trades suficientes todavía.",
                })
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(recommendations, key=lambda x: priority_order.get(x["priority"], 9))

    def get_platform_u_history(self, platform_name: str, limit: int = 100) -> List[Dict]:
        summary = self.get_platform_summary(platform_name)
        if summary.get("u_score", {}).get("current") is None:
            return []
        history_payload = self._read_platform_u_history(platform_name)
        history = history_payload.get("history", []) if isinstance(history_payload, dict) else []
        if not isinstance(history, list):
            return []
        return list(history[-limit:])

    def _synthetic_platform_activity(self, platform_name: str) -> List[Dict[str, Any]]:
        summary = self.get_platform_summary(platform_name)
        execution = summary.get("execution", {}) if isinstance(summary, dict) else {}
        rows: List[Dict[str, Any]] = []
        if platform_name == "ibkr":
            captured_utc = summary.get("timestamp")
            for pos in execution.get("live_positions", []) or []:
                qty = _safe_float(pos.get("position"))
                rows.append({
                    "timestamp": captured_utc,
                    "strategy_id": "broker_position",
                    "strategy": "broker_position",
                    "symbol": pos.get("symbol"),
                    "direction": "long" if qty > 0 else "short" if qty < 0 else "flat",
                    "quantity": qty,
                    "sec_type": pos.get("secType"),
                    "profit": None,
                    "resolved": False,
                    "execution_type": "broker_position",
                })
        elif platform_name == "pocket_option" and execution.get("last_browser_command_utc"):
            rows.append({
                "timestamp": execution.get("last_browser_command_utc"),
                "strategy_id": "browser_activity",
                "strategy": "browser_activity",
                "symbol": execution.get("last_browser_command_symbol"),
                "direction": "--",
                "profit": None,
                "resolved": False,
                "execution_type": "browser_ui_confirmed" if execution.get("last_browser_command_confirmed") else "browser_click_unverified",
            })
        return rows

    def get_platform_trade_history(self, platform_name: str, limit: int = 50) -> List[Dict]:
        platform_trades = self._platform_entries(platform_name)
        ordered = list(enumerate(platform_trades))
        ordered.sort(
            key=lambda item: (
                str(item[1].get("resolved_utc") or item[1].get("timestamp") or ""),
                item[0],
            ),
            reverse=True,
        )
        enriched = []
        for _, entry in ordered[:limit]:
            cloned = dict(entry)
            browser_order = cloned.get("browser_order") if isinstance(cloned.get("browser_order"), dict) else {}
            cloned["browser_trade_confirmed"] = bool(
                cloned.get("browser_trade_confirmed")
                or browser_order.get("ui_trade_confirmed")
            )
            cloned["browser_click_submitted"] = bool(
                browser_order.get("click_submitted")
                or cloned.get("browser_command_dispatched")
            )
            if cloned.get("venue") == "pocket_option":
                if cloned.get("browser_trade_confirmed"):
                    cloned["execution_type"] = "browser_ui_confirmed"
                elif cloned.get("browser_click_submitted"):
                    cloned["execution_type"] = "browser_click_unverified"
                else:
                    cloned["execution_type"] = "paper_shadow_only"
            elif cloned.get("paper_shadow"):
                cloned["execution_type"] = "paper_shadow"
            else:
                cloned["execution_type"] = "unknown"
            enriched.append(cloned)
        if enriched:
            return enriched
        synthetic = self._synthetic_platform_activity(platform_name)
        return synthetic[:limit]

    def compare_platforms(self) -> Dict[str, Any]:
        platforms = ["pocket_option", "ibkr", "internal_paper"]
        platform_summaries = {platform: self.get_platform_summary(platform) for platform in platforms}

        def rank_key(item: tuple[str, Dict[str, Any]]) -> tuple[Any, ...]:
            data = item[1]
            display_u = _optional_float(data.get("u_score", {}).get("current"))
            reference_trades = _safe_int(
                data.get("metrics", {}).get("reference_total_trades")
                if data.get("metrics", {}).get("reference_total_trades") is not None
                else data.get("metrics", {}).get("total_trades")
            )
            return (
                1 if data.get("status") == "active" else 0,
                1 if display_u is not None else 0,
                1 if reference_trades >= 5 else 0,
                display_u if display_u is not None else -999.0,
                _safe_int(data.get("ready_signals")),
                reference_trades,
            )

        def performance_key(item: tuple[str, Dict[str, Any]]) -> tuple[Any, ...]:
            data = item[1]
            display_u = _optional_float(data.get("u_score", {}).get("current"))
            return (
                1 if data.get("status") != "idle" else 0,
                1 if display_u is not None else 0,
                display_u if display_u is not None else -999.0,
                _safe_float(data.get("metrics", {}).get("reference_total_profit")),
                _safe_float(data.get("metrics", {}).get("reference_win_rate")),
                _safe_int(data.get("metrics", {}).get("reference_total_trades")),
            )

        ranked = sorted(
            platform_summaries.items(),
            key=rank_key,
            reverse=True,
        )
        performance_ranked = sorted(
            platform_summaries.items(),
            key=performance_key,
            reverse=True,
        )
        ranking = []
        for idx, (platform, data) in enumerate(ranked, 1):
            display_u = _optional_float(data.get("u_score", {}).get("current"))
            ranking.append({
                "rank": idx,
                "platform": platform,
                "u_score": _round(display_u) if display_u is not None else None,
                "u_basis": data.get("u_score", {}).get("display_basis"),
                "u_verdict": data.get("u_score", {}).get("verdict"),
                "win_rate": _optional_float(data.get("metrics", {}).get("reference_win_rate")),
                "profit": _optional_float(data.get("metrics", {}).get("reference_total_profit")),
                "trades": data.get("metrics", {}).get("reference_total_trades"),
                "metrics_basis": data.get("metrics", {}).get("reference_basis"),
                "status": data.get("status", "unknown"),
            })
        numeric_rows = [row for row in ranking if row.get("u_score") is not None]
        return {
            "generated_utc": _utc_now_iso(),
            "ranking": ranking,
            "best_performer": performance_ranked[0][0] if performance_ranked else None,
            "worst_performer": performance_ranked[-1][0] if performance_ranked else None,
            "summary": {
                "total_platforms": len(ranking),
                "active_platforms": sum(1 for row in ranking if row.get("status") == "active"),
                "average_u": _round(sum(row["u_score"] for row in numeric_rows) / len(numeric_rows)) if numeric_rows else None,
            },
        }

    def get_platform_signals_analysis(self, platform_name: str) -> Dict[str, Any]:
        platform_signals = self._platform_signals(platform_name)
        features = self._platform_features(platform_name)
        analysis = {
            "platform": platform_name,
            "timestamp": _utc_now_iso(),
            "total_signals": len(platform_signals),
            "valid_signals": sum(1 for s in platform_signals if s.get("signal_valid")),
            "execution_ready": self._platform_ready_signals_now(platform_name),
            "probation_ready": self._platform_probation_signals(platform_name),
            "avg_confidence": None,
            "problems": [],
            "recommendations": [],
        }
        if platform_signals:
            confidences = [_safe_float(s.get("confidence")) for s in platform_signals]
            analysis["avg_confidence"] = sum(confidences) / len(confidences)
            for signal in platform_signals:
                blockers = signal.get("blockers", [])
                if blockers:
                    analysis["problems"].append({
                        "strategy": signal.get("strategy_id"),
                        "blockers": blockers,
                    })
            if not analysis["execution_ready"]:
                analysis["recommendations"].append("No hay señales execution_ready en este momento.")
            elif analysis["probation_ready"]:
                analysis["recommendations"].append("Las señales listas actuales están en probation; conviene usarlas como exploración controlada, no como edge confirmado.")
        if features and any(bool(item.get("is_stale")) for item in features):
            analysis["recommendations"].append("Hay features stale en este venue.")
        return analysis


_platform_dashboard_api: Any = None


def get_platform_dashboard_api():
    """Obtiene instancia singleton del API."""
    global _platform_dashboard_api
    if _platform_dashboard_api is None:
        _platform_dashboard_api = PlatformDashboardAPI()
    return _platform_dashboard_api
