"""
Brain Chat V9 — trading/connectors.py
TiingoConnector, QuantConnectConnector, IBKRReadonlyConnector, PocketOptionBridge
Extraído de V8.0 líneas 2973-3417.
Corrección: paths de secrets desde config.py en lugar de hardcoded.
"""
import asyncio
import json
import logging
import socket
from base64 import b64encode
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Optional

from aiohttp import ClientSession, ClientTimeout

from brain_v9.config import (
    SECRETS, IBKR_HOST, IBKR_PORT, 
    IBKR_LANE_ARTIFACT, IBKR_PROBE_ARTIFACT, IBKR_PROBE_STATUS_ARTIFACT,
    IBKR_ORDER_CHECK_ARTIFACT,
    PO_BRIDGE_LATEST_ARTIFACT, PO_FEED_ARTIFACT, PO_DUE_DILIGENCE_ARTIFACT,
    PO_COMMAND_RESULT_ARTIFACT,
)
from brain_v9.core.state_io import read_json

log = logging.getLogger("connectors")
_PO_BROWSER_COMMAND_WAIT_SECONDS = 90


def _safe_read_json(path: Path) -> Dict:
    return read_json(path, {})


def _mtime_utc(path: Path) -> Optional[str]:
    try:
        if path.exists():
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception as exc:
        log.debug("_mtime_utc failed for %s: %s", path, exc)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Base mixin para sesión lazy
# ─────────────────────────────────────────────────────────────────────────────
class _SessionMixin:
    _session: Optional[ClientSession] = None

    async def _get_session(self, timeout: int = 30) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(timeout=ClientTimeout(total=timeout))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()


# ─────────────────────────────────────────────────────────────────────────────
# Tiingo
# ─────────────────────────────────────────────────────────────────────────────
class TiingoConnector(_SessionMixin):
    BASE_URL = "https://api.tiingo.com"

    def __init__(self, token: Optional[str] = None):
        self.logger = logging.getLogger("TiingoConnector")
        creds = self._load_secrets(SECRETS["tiingo"])
        self.token = token or creds.get("token", "")
        if not self.token:
            self.logger.warning("Tiingo: token no configurado")

    def _load_secrets(self, path: Path) -> Dict:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            self.logger.warning("No se pudieron cargar secrets de Tiingo: %s", e)
        return {}

    def _headers(self) -> Dict:
        return {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}

    async def check_health(self) -> Dict:
        try:
            s = await self._get_session()
            async with s.get(f"{self.BASE_URL}/api/test", headers=self._headers()) as r:
                return {
                    "success": r.status == 200,
                    "status_code": r.status,
                    "mode": "read_only",
                    "current_capability": "daily_and_intraday_features" if r.status == 200 else "auth_failed",
                    "paper_trading_allowed": False,
                    "live_trading_allowed": False,
                    "recommended_usage": "feature_enrichment_and_history",
                    "next_enablement_step": "Usar Tiingo para features históricas/intradía y validación cruzada, no para ejecución.",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_intraday_data(self, symbol: str, start_date=None, end_date=None, resample_freq="1min") -> Dict:
        try:
            params = {"resampleFreq": resample_freq}
            if start_date: params["startDate"] = start_date
            if end_date:   params["endDate"]   = end_date
            s = await self._get_session()
            async with s.get(f"{self.BASE_URL}/iex/{symbol}", headers=self._headers(), params=params) as r:
                if r.status != 200:
                    return {"success": False, "error": f"HTTP {r.status}"}
                return {"success": True, "data": await r.json(), "symbol": symbol}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_historical_data(self, symbol: str, days: int = 30) -> Dict:
        from datetime import datetime, timedelta
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            s = await self._get_session()
            async with s.get(
                f"{self.BASE_URL}/tiingo/daily/{symbol}/prices",
                headers=self._headers(),
                params={"startDate": start, "endDate": end},
            ) as r:
                if r.status != 200:
                    return {"success": False, "error": f"HTTP {r.status}"}
                return {"success": True, "data": await r.json(), "symbol": symbol, "days": days}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# QuantConnect
# ─────────────────────────────────────────────────────────────────────────────
class QuantConnectConnector(_SessionMixin):
    BASE_URL = "https://www.quantconnect.com/api/v2"

    def __init__(self, user_id: Optional[str] = None, token: Optional[str] = None):
        self.logger = logging.getLogger("QuantConnectConnector")
        creds = self._load_secrets(SECRETS["quantconnect"])
        self.user_id = user_id or creds.get("user_id", "")
        self.token   = token   or creds.get("token",   "")
        if not self.user_id or not self.token:
            self.logger.warning("QuantConnect: credenciales no configuradas")

    def _load_secrets(self, path: Path) -> Dict:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            self.logger.warning("No se pudieron cargar secrets de QC: %s", e)
        return {}

    def _headers(self) -> Dict:
        import time
        timestamp = str(int(time.time()))
        # QuantConnect espera SHA256(API_TOKEN:timestamp) y luego Basic base64(USER_ID:hash).
        time_stamped_token = f"{self.token}:{timestamp}".encode("utf-8")
        hashed_token = sha256(time_stamped_token).hexdigest()
        auth = b64encode(f"{self.user_id}:{hashed_token}".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {auth}",
            "Timestamp": timestamp,
            "Content-Type": "application/json",
        }

    async def check_health(self) -> Dict:
        try:
            s = await self._get_session()
            headers = self._headers()
            async with s.post(f"{self.BASE_URL}/authenticate", headers=headers, json={}) as r:
                payload = await r.json(content_type=None)
                success = r.status == 200 and bool(payload.get("success"))
                projects_count = 0
                if success:
                    async with s.post(f"{self.BASE_URL}/projects/read", headers=self._headers(), json={}) as pr:
                        proj_payload = await pr.json(content_type=None)
                        projects_count = len(proj_payload.get("projects", []))
                return {
                    "success": success,
                    "status_code": r.status,
                    "mode": "research_only",
                    "current_capability": "research_projects_and_files" if success else "auth_failed",
                    "paper_trading_allowed": False,
                    "live_trading_allowed": False,
                    "recommended_usage": "research_only",
                    "response_preview": payload,
                    "projects_count": projects_count,
                    "next_enablement_step": (
                        "Usar QuantConnect para research, proyectos, datasets y backtests; no como lane de ejecución."
                        if success else
                        "Revisar token/UserID o policy de API en QuantConnect."
                    ),
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_projects(self) -> Dict:
        try:
            s = await self._get_session()
            async with s.post(f"{self.BASE_URL}/projects/read", headers=self._headers(), json={}) as r:
                payload = await r.json(content_type=None)
                projects = payload.get("projects", [])
                return {
                    "success": r.status == 200 and not payload.get("errors"),
                    "status_code": r.status,
                    "projects_count": len(projects),
                    "projects": projects,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_project_file(self, project_id: int, name: str = "main.py") -> Dict:
        try:
            s = await self._get_session()
            body = {"projectId": int(project_id), "name": name}
            async with s.post(f"{self.BASE_URL}/files/read", headers=self._headers(), json=body) as r:
                payload = await r.json(content_type=None)
                files = payload.get("files", [])
                return {
                    "success": r.status == 200 and not payload.get("errors"),
                    "status_code": r.status,
                    "files_count": len(files),
                    "files": files,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_historical_data(self, symbol: str, days: int = 30) -> Dict:
        # QC no se usa como market data lane intradía aquí; se expone como research metadata/projects.
        projects = await self.get_projects()
        return {
            "success": projects.get("success", False),
            "symbol": symbol,
            "days": days,
            "mode": "research_only",
            "message": "QuantConnect se usa como capa de research/proyectos, no como feed directo en este Brain.",
            "projects_count": projects.get("projects_count", 0),
            "projects": projects.get("projects", [])[:5],
        }

    # ── P4-08: Compile + Backtest lifecycle ──────────────────────────────────

    async def compile_project(self, project_id: int) -> Dict:
        """Trigger compilation for *project_id*. Returns compileId + state."""
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id)}
            async with s.post(
                f"{self.BASE_URL}/compile/create",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "compile_id": payload.get("compileId", ""),
                    "state": payload.get("state", ""),
                    "errors": payload.get("errors", []),
                    "raw": payload,
                }
        except Exception as e:
            self.logger.error("compile_project failed: %s", e)
            return {"success": False, "error": str(e)}

    async def read_compile(self, project_id: int, compile_id: str) -> Dict:
        """Poll compilation status until BuildSuccess / BuildError."""
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id), "compileId": compile_id}
            async with s.post(
                f"{self.BASE_URL}/compile/read",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                state = payload.get("state", "")
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "compile_id": payload.get("compileId", compile_id),
                    "state": state,
                    "build_success": state == "BuildSuccess",
                    "build_error": state == "BuildError",
                    "errors": payload.get("errors", []),
                    "raw": payload,
                }
        except Exception as e:
            self.logger.error("read_compile failed: %s", e)
            return {"success": False, "error": str(e)}

    async def create_backtest(
        self,
        project_id: int,
        compile_id: str,
        backtest_name: str = "Brain V9 Backtest",
    ) -> Dict:
        """Launch a cloud backtest. Returns backtestId (async — must poll)."""
        try:
            s = await self._get_session(timeout=60)
            body = {
                "projectId": int(project_id),
                "compileId": compile_id,
                "backtestName": backtest_name,
            }
            async with s.post(
                f"{self.BASE_URL}/backtests/create",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                bt = payload.get("backtest", {})
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "backtest_id": bt.get("backtestId", ""),
                    "name": bt.get("name", backtest_name),
                    "completed": bt.get("completed", False),
                    "status": bt.get("status", ""),
                    "progress": bt.get("progress", 0),
                    "error": bt.get("error", ""),
                    "errors": payload.get("errors", []),
                    "raw": payload,
                }
        except Exception as e:
            self.logger.error("create_backtest failed: %s", e)
            return {"success": False, "error": str(e)}

    async def read_backtest(self, project_id: int, backtest_id: str) -> Dict:
        """Read / poll a single backtest. Contains full results when completed."""
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id), "backtestId": backtest_id}
            async with s.post(
                f"{self.BASE_URL}/backtests/read",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                bt = payload.get("backtest") or {}  # API returns null for deleted backtests
                stats = bt.get("statistics", {})
                runtime = bt.get("runtimeStatistics", {})
                perf = bt.get("totalPerformance", {})
                portfolio_stats = perf.get("portfolioStatistics", {})
                trade_stats = perf.get("tradeStatistics", {})
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "backtest_id": bt.get("backtestId", backtest_id),
                    "name": bt.get("name", ""),
                    "completed": bt.get("completed", False),
                    "status": bt.get("status", ""),
                    "progress": bt.get("progress", 0),
                    "error": bt.get("error", ""),
                    "stacktrace": bt.get("stacktrace", ""),
                    "has_initialize_error": bt.get("hasInitializeError", False),
                    # Flat statistics (all strings)
                    "statistics": stats,
                    "runtime_statistics": runtime,
                    # Structured performance
                    "portfolio_statistics": portfolio_stats,
                    "trade_statistics": trade_stats,
                    # Key metrics extracted for convenience
                    "metrics": {
                        "sharpe_ratio": stats.get("Sharpe Ratio", ""),
                        "sortino_ratio": stats.get("Sortino Ratio", ""),
                        "compounding_annual_return": stats.get("Compounding Annual Return", ""),
                        "drawdown": stats.get("Drawdown", ""),
                        "net_profit": stats.get("Net Profit", ""),
                        "win_rate": stats.get("Win Rate", ""),
                        "loss_rate": stats.get("Loss Rate", ""),
                        "expectancy": stats.get("Expectancy", ""),
                        "total_orders": stats.get("Total Orders", ""),
                        "profit_loss_ratio": stats.get("Profit-Loss Ratio", ""),
                        "alpha": stats.get("Alpha", ""),
                        "beta": stats.get("Beta", ""),
                    },
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("read_backtest failed: %s", e)
            return {"success": False, "error": str(e)}

    async def list_backtests(
        self, project_id: int, include_statistics: bool = True
    ) -> Dict:
        """List all backtests for *project_id*."""
        try:
            s = await self._get_session(timeout=60)
            body = {
                "projectId": int(project_id),
                "includeStatistics": include_statistics,
            }
            async with s.post(
                f"{self.BASE_URL}/backtests/list",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                backtests = payload.get("backtests", [])
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "count": payload.get("count", len(backtests)),
                    "backtests": backtests,
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("list_backtests failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── Project & File management (needed for strategy deployment) ───────────

    async def create_project(
        self, name: str, language: str = "Py"
    ) -> Dict:
        """Create a new QC project. Returns projectId."""
        try:
            s = await self._get_session(timeout=60)
            body = {"name": name, "language": language}
            async with s.post(
                f"{self.BASE_URL}/projects/create",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                projects = payload.get("projects", [])
                project = projects[0] if projects else {}
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "project_id": project.get("projectId", 0),
                    "name": project.get("name", name),
                    "raw": payload,
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("create_project failed: %s", e)
            return {"success": False, "error": str(e)}

    async def create_file(
        self, project_id: int, name: str, content: str
    ) -> Dict:
        """Create a new file inside a QC project."""
        try:
            s = await self._get_session(timeout=60)
            body = {
                "projectId": int(project_id),
                "name": name,
                "content": content,
            }
            async with s.post(
                f"{self.BASE_URL}/files/create",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                files = payload.get("files", [])
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "files": files,
                    "raw": payload,
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("create_file failed: %s", e)
            return {"success": False, "error": str(e)}

    async def update_file(
        self, project_id: int, name: str, content: str
    ) -> Dict:
        """Update an existing file inside a QC project."""
        try:
            s = await self._get_session(timeout=60)
            body = {
                "projectId": int(project_id),
                "name": name,
                "content": content,
            }
            async with s.post(
                f"{self.BASE_URL}/files/update",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "raw": payload,
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("update_file failed: %s", e)
            return {"success": False, "error": str(e)}

    async def delete_file(
        self, project_id: int, name: str
    ) -> Dict:
        """Delete a file from a QC project."""
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id), "name": name}
            async with s.post(
                f"{self.BASE_URL}/files/delete",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "raw": payload,
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("delete_file failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── QC Live Trading lifecycle ────────────────────────────────────────────

    async def deploy_live(
        self,
        project_id: int,
        compile_id: str,
        node_id: str,
        brokerage: Dict,
        data_providers: Optional[Dict] = None,
        version_id: str = "-1",
    ) -> Dict:
        """Deploy a live algorithm on QC Cloud.

        Parameters
        ----------
        project_id : int
            QC project ID (e.g. 29490680).
        compile_id : str
            CompileId from a successful compile.
        node_id : str
            Live node ID (e.g. "LN-...").
        brokerage : dict
            Brokerage config including credentials.  Example for IBKR::

                {
                    "id": "InteractiveBrokersBrokerage",
                    "ib-user-name": "...",
                    "ib-account": "DUM891854",
                    "ib-password": "...",
                    "ib-weekly-restart-utc-time": "22:00:00"
                }
        data_providers : dict, optional
            Data provider config.  Defaults to IBKR-as-data-provider.
        version_id : str
            "-1" for latest version (default).

        Returns
        -------
        dict
            Includes success, deploy_id, status, and raw API response.
        """
        if data_providers is None:
            brokerage_id = brokerage.get("id", "InteractiveBrokersBrokerage")
            data_providers = {brokerage_id: {"id": brokerage_id}}
        try:
            s = await self._get_session(timeout=120)
            body = {
                "versionId": version_id,
                "projectId": int(project_id),
                "compileId": compile_id,
                "nodeId": node_id,
                "brokerage": brokerage,
                "dataProviders": data_providers,
            }
            self.logger.info(
                "deploy_live: project=%s node=%s brokerage=%s",
                project_id, node_id, brokerage.get("id"),
            )
            async with s.post(
                f"{self.BASE_URL}/live/create",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                success = r.status == 200 and bool(payload.get("success"))
                deploy_id = payload.get("deployId", "")
                status = payload.get("status", "")
                if not success:
                    self.logger.error(
                        "deploy_live FAILED: HTTP %s — %s",
                        r.status, payload.get("errors") or payload.get("messages"),
                    )
                else:
                    self.logger.info(
                        "deploy_live OK: deployId=%s status=%s", deploy_id, status,
                    )
                return {
                    "success": success,
                    "status_code": r.status,
                    "deploy_id": deploy_id,
                    "status": status,
                    "project_id": project_id,
                    "node_id": node_id,
                    "errors": payload.get("errors", []),
                    "raw": payload,
                }
        except Exception as e:
            self.logger.error("deploy_live failed: %s", e)
            return {"success": False, "error": str(e)}

    async def read_live(self, project_id: int, deploy_id: str) -> Dict:
        """Read status and performance of a running live algorithm.

        Returns equity, holdings, runtime stats, orders, and state.
        """
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id), "deployId": deploy_id}
            async with s.post(
                f"{self.BASE_URL}/live/read",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                # QC API returns data at root level OR nested under LiveResults.Results
                live = payload.get("LiveResults") or payload.get("live") or {}
                results = live.get("Results") or live.get("results") or {}
                # Try root-level first (how QC actually returns it), then nested
                runtime = (payload.get("runtimeStatistics")
                           or results.get("RuntimeStatistics")
                           or results.get("runtimeStatistics") or {})
                stats = (payload.get("statistics")
                         or results.get("Statistics")
                         or results.get("statistics") or {})
                holdings = (payload.get("holdings")
                            or results.get("Holdings")
                            or results.get("holdings") or {})
                orders = (payload.get("orders")
                          or results.get("Orders")
                          or results.get("orders") or {})
                cash = (payload.get("cash")
                        or results.get("Cash")
                        or results.get("cash") or {})
                charts = (payload.get("charts")
                          or results.get("Charts")
                          or results.get("charts") or {})

                # Extract equity curve from "Strategy Equity" chart if present
                equity_points = []
                strategy_equity = charts.get("Strategy Equity", {})
                if strategy_equity:
                    series = strategy_equity.get("Series", strategy_equity.get("series", {}))
                    eq_series = series.get("Equity", series.get("equity", {}))
                    eq_values = eq_series.get("Values", eq_series.get("values", []))
                    equity_points = [
                        {"x": pt.get("x", 0), "y": pt.get("y", 0)}
                        for pt in eq_values[-500:]  # last 500 points max
                    ]

                return {
                    "success": r.status == 200 and bool(payload.get("success", True)),
                    "status_code": r.status,
                    "deploy_id": deploy_id,
                    "project_id": project_id,
                    "state": payload.get("State") or payload.get("state") or "",
                    "launched_utc": payload.get("launched") or "",
                    "stopped_utc": payload.get("stopped") or "",
                    "runtime_statistics": runtime,
                    "statistics": stats,
                    "holdings": holdings,
                    "holdings_count": len(holdings),
                    "orders_count": len(orders) if isinstance(orders, dict) else 0,
                    "cash": cash,
                    "equity_curve": equity_points,
                    "metrics": {
                        "equity": runtime.get("Equity", ""),
                        "net_profit": runtime.get("Net Profit", ""),
                        "return_pct": runtime.get("Return", ""),
                        "unrealized": runtime.get("Unrealized", ""),
                        "holdings_value": runtime.get("Holdings", ""),
                        "volume": runtime.get("Volume", ""),
                        "sharpe_ratio": stats.get("Sharpe Ratio", ""),
                        "drawdown": stats.get("Drawdown", ""),
                        "win_rate": stats.get("Win Rate", ""),
                        "total_orders": stats.get("Total Orders", ""),
                    },
                    "errors": payload.get("errors", []),
                    "raw_keys": list(payload.keys()),
                }
        except Exception as e:
            self.logger.error("read_live failed: %s", e)
            return {"success": False, "error": str(e)}

    async def stop_live(self, project_id: int) -> Dict:
        """Stop a running live algorithm. QC stops by projectId."""
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id)}
            async with s.post(
                f"{self.BASE_URL}/live/update/stop",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                success = r.status == 200 and bool(payload.get("success"))
                if success:
                    self.logger.info("stop_live OK: project=%s", project_id)
                else:
                    self.logger.error(
                        "stop_live FAILED: HTTP %s — %s",
                        r.status, payload.get("errors"),
                    )
                return {
                    "success": success,
                    "status_code": r.status,
                    "project_id": project_id,
                    "errors": payload.get("errors", []),
                    "raw": payload,
                }
        except Exception as e:
            self.logger.error("stop_live failed: %s", e)
            return {"success": False, "error": str(e)}

    async def liquidate_live(self, project_id: int) -> Dict:
        """Liquidate all positions and stop a running live algorithm."""
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id)}
            async with s.post(
                f"{self.BASE_URL}/live/update/liquidate",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                success = r.status == 200 and bool(payload.get("success"))
                if success:
                    self.logger.info("liquidate_live OK: project=%s", project_id)
                else:
                    self.logger.error(
                        "liquidate_live FAILED: HTTP %s — %s",
                        r.status, payload.get("errors"),
                    )
                return {
                    "success": success,
                    "status_code": r.status,
                    "project_id": project_id,
                    "errors": payload.get("errors", []),
                    "raw": payload,
                }
        except Exception as e:
            self.logger.error("liquidate_live failed: %s", e)
            return {"success": False, "error": str(e)}

    async def list_live(self, status: str = "Running", start: int = 0, end: int = 50) -> Dict:
        """List live algorithms filtered by status.

        Parameters
        ----------
        status : str
            Filter: "Running", "Stopped", "RuntimeError", "Liquidated", etc.
        start : int
            Pagination start index.
        end : int
            Pagination end index.

        Returns
        -------
        dict
            List of live deployments with their metadata.
        """
        try:
            s = await self._get_session(timeout=60)
            body = {"status": status, "start": start, "end": end}
            async with s.post(
                f"{self.BASE_URL}/live/list",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                live_list = payload.get("live", [])
                return {
                    "success": r.status == 200 and bool(payload.get("success")),
                    "status_code": r.status,
                    "count": len(live_list),
                    "live": [
                        {
                            "deploy_id": dep.get("deployId", ""),
                            "project_id": dep.get("projectId", 0),
                            "status": dep.get("status", ""),
                            "launched": dep.get("launched", ""),
                            "stopped": dep.get("stopped", ""),
                            "brokerage": dep.get("brokerage", ""),
                            "note": dep.get("note", ""),
                            "error": dep.get("error", ""),
                        }
                        for dep in live_list
                    ],
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("list_live failed: %s", e)
            return {"success": False, "error": str(e)}

    async def read_live_portfolio(self, project_id: int, deploy_id: str) -> Dict:
        """Convenience: extract holdings + cash + P&L from read_live."""
        data = await self.read_live(project_id, deploy_id)
        if not data.get("success"):
            return data
        return {
            "success": True,
            "deploy_id": deploy_id,
            "state": data.get("state", ""),
            "equity": data.get("metrics", {}).get("equity", ""),
            "net_profit": data.get("metrics", {}).get("net_profit", ""),
            "return_pct": data.get("metrics", {}).get("return_pct", ""),
            "unrealized": data.get("metrics", {}).get("unrealized", ""),
            "holdings_count": data.get("holdings_count", 0),
            "holdings": data.get("holdings", {}),
            "cash": data.get("cash", {}),
        }

    async def read_live_holdings(self, project_id: int) -> Dict:
        """Read detailed holdings from QC Live portfolio endpoint.

        Uses /live/portfolio/read which returns per-symbol holdings
        with abbreviated keys: a=avgPrice, q=quantity, p=price, v=value,
        u=unrealizedPnl, up=unrealizedPnlPct.
        """
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id)}
            async with s.post(
                f"{self.BASE_URL}/live/portfolio/read",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                portfolio = payload.get("portfolio", {})
                raw_holdings = portfolio.get("holdings", {})
                cash_data = portfolio.get("cash", {})

                # Expand abbreviated keys for readability
                holdings = {}
                for sym, h in raw_holdings.items():
                    if isinstance(h, dict):
                        holdings[sym] = {
                            "symbol": sym,
                            "avgPrice": h.get("a", 0),
                            "quantity": h.get("q", 0),
                            "price": h.get("p", 0),
                            "value": h.get("v", 0),
                            "unrealizedPnl": h.get("u", 0),
                            "unrealizedPnlPct": h.get("up", 0),
                        }

                return {
                    "success": r.status == 200 and bool(payload.get("success", True)),
                    "holdings": holdings,
                    "holdings_count": len(holdings),
                    "cash": cash_data,
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("read_live_holdings failed: %s", e)
            return {"success": False, "error": str(e)}

    async def read_live_orders(self, project_id: int, start: int = 0, end: int = 100) -> Dict:
        """Read live algorithm orders from QC API.

        Uses /live/orders/read with start/end pagination.
        """
        try:
            s = await self._get_session(timeout=60)
            body = {"projectId": int(project_id), "start": start, "end": end}
            async with s.post(
                f"{self.BASE_URL}/live/orders/read",
                headers=self._headers(),
                json=body,
            ) as r:
                payload = await r.json(content_type=None)
                orders = payload.get("orders", [])
                return {
                    "success": r.status == 200 and bool(payload.get("success", True)),
                    "orders": orders,
                    "total": len(orders),
                    "errors": payload.get("errors", []),
                }
        except Exception as e:
            self.logger.error("read_live_orders failed: %s", e)
            return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# IBKR readonly
# ─────────────────────────────────────────────────────────────────────────────
class IBKRReadonlyConnector:
    def __init__(self, host: str = IBKR_HOST, port: int = IBKR_PORT):
        self.logger = logging.getLogger("IBKRReadonlyConnector")
        self.host = host
        self.port = port
        self.lane_artifact = IBKR_LANE_ARTIFACT
        self.probe_artifact = IBKR_PROBE_ARTIFACT
        self.probe_status_artifact = IBKR_PROBE_STATUS_ARTIFACT
        self.order_check_artifact = IBKR_ORDER_CHECK_ARTIFACT

    async def check_health(self) -> Dict:
        # FIX (2026-03-30): Try socket connection FIRST, only fall back to
        # file artifacts when the gateway is genuinely offline.  Previous code
        # short-circuited to stale file data whenever order_check had
        # "order_api_ready", even when the gateway was actually running.
        from datetime import datetime, timezone, timedelta
        
        lane = _safe_read_json(self.lane_artifact)
        probe = _safe_read_json(self.probe_artifact)
        probe_status = _safe_read_json(self.probe_status_artifact)
        order_check = _safe_read_json(self.order_check_artifact)
        
        # -- Step 1: Always try socket connection first --
        port_open = False
        connect_code = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            connect_code = sock.connect_ex((self.host, self.port))
            port_open = connect_code == 0
            sock.close()
        except Exception:
            port_open = False

        # -- Step 2: If socket is open, use live connection data --
        if port_open:
            errors = probe.get("errors", [])
            subscription_errors = [err for err in errors if err.get("errorCode") in {10089, 10167, 10168}]
            farms_ok = [err for err in errors if err.get("errorCode") in {2104, 2106, 2158}]
            probe_connected = bool(probe.get("connected"))
            market_data_api_ready = probe_connected and not subscription_errors
            order_api_ready = bool(order_check.get("order_api_ready"))
            paper_shadow_allowed = market_data_api_ready
            order_api_blocking_reason = order_check.get("blocking_reason")
            if not order_api_blocking_reason and order_check.get("errors"):
                first_error = order_check["errors"][0]
                order_api_blocking_reason = f"{first_error.get('errorCode')}:{first_error.get('errorString', '')[:160]}"
            if order_api_ready:
                order_api_blocking_reason = None
            if not order_api_blocking_reason:
                order_api_blocking_reason = None
            next_enablement_step = "Mantener IBKR Gateway paper en 4002 y validar market data API con A/B/C + OPRA activas."
            if market_data_api_ready and not order_api_ready:
                next_enablement_step = "El feed ya sirve; falta habilitar el socket/API de ordenes paper en Gateway y repetir paper-order-check."
            elif market_data_api_ready and order_api_ready:
                next_enablement_step = "Lane listo para market data y ordenes paper; mantener paper_only y empezar pruebas controladas por estrategia."
            return {
                "success": True,
                "provider": "ibkr",
                "display_name": "Interactive Brokers",
                "mode": lane.get("mode", "read_only_first"),
                "host": self.host,
                "port": self.port,
                "port_open": True,
                "connect_code": connect_code,
                "data_source": "socket_connection",
                "last_probe_connected": probe_connected,
                "last_probe_checked_utc": probe.get("checked_utc"),
                "last_probe_errors": errors[:5],
                "last_probe_artifact_utc": _mtime_utc(self.probe_artifact),
                "lane_artifact_utc": _mtime_utc(self.lane_artifact),
                "probe_status_artifact_utc": _mtime_utc(self.probe_status_artifact),
                "order_check_artifact_utc": _mtime_utc(self.order_check_artifact),
                "market_data_api_ready": market_data_api_ready,
                "paper_market_data_allowed": market_data_api_ready,
                "paper_shadow_allowed": paper_shadow_allowed,
                "order_api_ready": order_api_ready,
                "order_api_blocking_reason": order_api_blocking_reason,
                "subscription_errors": subscription_errors[:5],
                "farms_ok": len(farms_ok),
                "paper_trading_allowed": order_api_ready,
                "live_trading_allowed": False,
                "read_only_allowed": True,
                "allowed_actions": lane.get("allowed_actions", []),
                "forbidden_for_now": lane.get("forbidden_for_now", []),
                "accounts_visible": probe_status.get("accounts") or probe_status.get("managed_accounts") or [],
                "next_enablement_step": next_enablement_step,
                "status": "available" if market_data_api_ready else "degraded",
            }

        # -- Step 3: Socket closed — fall back to file artifacts --
        order_check_time_str = order_check.get("checked_utc")
        order_check_fresh = False
        if order_check_time_str:
            try:
                order_time = datetime.fromisoformat(order_check_time_str.replace('Z', '+00:00'))
                order_check_fresh = (datetime.now(timezone.utc) - order_time) < timedelta(hours=24)
            except Exception as exc:
                log.debug("IBKR order_check timestamp parse failed: %s", exc)
        
        if order_check.get("order_api_ready"):
            probe_time_str = probe.get("checked_utc")
            probe_fresh = False
            if probe_time_str:
                try:
                    probe_time = datetime.fromisoformat(probe_time_str.replace('Z', '+00:00'))
                    probe_fresh = (datetime.now(timezone.utc) - probe_time) < timedelta(hours=24)
                except Exception as exc:
                    log.debug("IBKR probe timestamp parse failed: %s", exc)
            
            errors = probe.get("errors", [])
            subscription_errors = [err for err in errors if err.get("errorCode") in {10089, 10167, 10168}]
            probe_connected = bool(probe.get("connected"))
            market_data_api_ready = probe_connected and not subscription_errors
            order_api_ready = bool(order_check.get("order_api_ready"))
            
            return {
                "success": True,
                "provider": "ibkr",
                "display_name": "Interactive Brokers",
                "mode": lane.get("mode", "read_only_first"),
                "host": self.host,
                "port": self.port,
                "port_open": False,
                "connect_code": connect_code,
                "data_source": "file_artifacts" + ("_recent" if order_check_fresh else "_historical"),
                "data_freshness": "fresh" if order_check_fresh else "stale",
                "last_probe_connected": probe_connected,
                "last_probe_checked_utc": probe.get("checked_utc"),
                "order_check_checked_utc": order_check.get("checked_utc"),
                "market_data_api_ready": market_data_api_ready,
                "paper_market_data_allowed": market_data_api_ready,
                "paper_shadow_allowed": market_data_api_ready,
                "order_api_ready": order_api_ready,
                "paper_trading_allowed": order_api_ready,
                "live_trading_allowed": False,
                "read_only_allowed": True,
                "status": "available" if order_api_ready else "degraded",
                "note": "IBKR Gateway offline (port closed), usando datos de archivo.",
                "next_enablement_step": "Reiniciar IBKR Gateway para restablecer conexión en tiempo real."
            }
        
        # -- Step 4: No file artifacts either --
        return {"success": False, "provider": "ibkr", "error": "gateway_offline_no_artifacts", "mode": "read_only_first"}

# ─────────────────────────────────────────────────────────────────────────────
# PocketOption Bridge
# ─────────────────────────────────────────────────────────────────────────────
class PocketOptionBridge(_SessionMixin):
    def __init__(self, bridge_url: Optional[str] = None):
        if bridge_url is None:
            bridge_url = os.getenv("POCKETOPTION_BRIDGE_URL", "")
        self.logger     = logging.getLogger("PocketOptionBridge")
        self.bridge_url = bridge_url
        self._session   = None
        self.logger     = logging.getLogger("PocketOptionBridge")
        self.bridge_url = bridge_url
        self.browser_bridge_artifact = PO_BRIDGE_LATEST_ARTIFACT
        self.browser_feed_artifact = PO_FEED_ARTIFACT
        self.due_diligence_artifact = PO_DUE_DILIGENCE_ARTIFACT
        self.last_command_result_artifact = PO_COMMAND_RESULT_ARTIFACT

    async def check_health(self) -> Dict:
        bridge_snapshot = _safe_read_json(self.browser_bridge_artifact)
        due_diligence = _safe_read_json(self.due_diligence_artifact)
        last_command = _safe_read_json(self.last_command_result_artifact)
        current = bridge_snapshot.get("current", {})
        dom = bridge_snapshot.get("dom", {})
        
        # Verificar si los archivos del browser bridge son recientes (< 24 horas)
        from datetime import datetime, timezone, timedelta
        bridge_time_str = bridge_snapshot.get("captured_utc")
        bridge_fresh = False
        if bridge_time_str:
            try:
                bridge_time = datetime.fromisoformat(bridge_time_str.replace('Z', '+00:00'))
                bridge_fresh = (datetime.now(timezone.utc) - bridge_time) < timedelta(hours=24)
            except Exception as exc:
                log.debug("PO bridge timestamp parse failed: %s", exc)
        
        # Usar archivos si son recientes O si no hay otra opción
        has_bridge_data = bool(bridge_snapshot.get("current", {}).get("symbol"))
        
        if has_bridge_data:
            # Datos del bridge son válidos, usar modo archivo
            last_result = last_command.get("result", {})
            manual_test = bool(last_result.get("evidence", {}).get("manual_test"))
            bad_button = str(last_result.get("evidence", {}).get("button_text") or "").strip().lower() == "top up"
            click_submitted = bool(last_result.get("accepted_click"))
            ui_trade_confirmed = bool(last_result.get("ui_trade_confirmed"))
            command_success = click_submitted and not manual_test and not bad_button
            confirmation_success = ui_trade_confirmed and command_success
            blocking_reason = None if command_success else (
                "browser_extension_not_reloaded_or_not_polling"
                if manual_test else
                ("invalid_button_detected_top_up" if bad_button else "demo_order_not_verified_yet")
            )
            confirmation_blocking_reason = None if confirmation_success else (blocking_reason or "ui_trade_not_confirmed")
            return {
                "success": True,
                "provider": "pocket_option",
                "display_name": "Pocket Option",
                "status": "available",
                "data_source": "browser_bridge_files",  # Indica que usa archivos, no HTTP
                "connected": True,
                "bridge_url": self.bridge_url,
                "paper_trading_allowed": True,
                "live_trading_allowed": False,
                "preferred_mode": "paper_only",
                "browser_bridge_last_capture_utc": bridge_snapshot.get("captured_utc"),
                "browser_bridge_artifact_utc": _mtime_utc(self.browser_bridge_artifact),
                "feed_artifact_utc": _mtime_utc(self.browser_feed_artifact),
                "socket_url": bridge_snapshot.get("ws", {}).get("last_socket_url"),
                "ws_event_count": bridge_snapshot.get("ws", {}).get("event_count"),
                "hook_mode": bridge_snapshot.get("ws", {}).get("hook_mode"),
                "last_stream_symbol": bridge_snapshot.get("ws", {}).get("last_stream_symbol"),
                "visible_symbol": bridge_snapshot.get("ws", {}).get("visible_symbol"),
                "stream_symbol_match": bridge_snapshot.get("ws", {}).get("stream_symbol_match"),
                "current_symbol": current.get("symbol"),
                "current_price": current.get("price"),
                "payout_pct": current.get("payout_pct") or dom.get("payout_pct"),
                "expiry_seconds": current.get("expiry_seconds") or dom.get("expiry_seconds"),
                "venue_classification": due_diligence.get("brain_decision", {}).get("venue_classification"),
                "demo_order_api_ready": command_success,
                "demo_order_api_blocking_reason": blocking_reason,
                "demo_order_ui_confirmation_ready": confirmation_success,
                "demo_order_ui_confirmation_blocking_reason": confirmation_blocking_reason,
                "recommended_usage": due_diligence.get("findings", [{}])[-1].get("assessment"),
                "next_enablement_step": (
                    "Lane demo listo para ejecucion browser-driven en paper_only."
                    if confirmation_success else
                    ("El bridge puede hacer click, pero falta confirmar que la UI registre la operacion."
                     if command_success else
                     "Verificar que la pagina demo este abierta y la extension recargada.")
                ),
            }
        
        # Fallback: intentar HTTP bridge
        try:
            s = await self._get_session(timeout=10)
            async with s.get(f"{self.bridge_url}/health") as r:
                data = await r.json()
                last_result = last_command.get("result", {})
                manual_test = bool(last_result.get("evidence", {}).get("manual_test"))
                bad_button = str(last_result.get("evidence", {}).get("button_text") or "").strip().lower() == "top up"
                click_submitted = bool(last_result.get("accepted_click"))
                ui_trade_confirmed = bool(last_result.get("ui_trade_confirmed"))
                command_success = click_submitted and not manual_test and not bad_button
                confirmation_success = ui_trade_confirmed and command_success
                blocking_reason = None if command_success else (
                    "browser_extension_not_reloaded_or_not_polling"
                    if manual_test else
                    (
                        "invalid_button_detected_top_up"
                        if bad_button else
                        (last_result.get("reason") or data.get("last_command_status") or "demo_order_not_verified_yet")
                    )
                )
                confirmation_blocking_reason = None if confirmation_success else (blocking_reason or "ui_trade_not_confirmed")
                return {
                    "success": r.status == 200,
                    "provider": "pocket_option",
                    "display_name": "Pocket Option",
                    "status": data.get("status") or ("available" if r.status == 200 else "degraded"),
                    "data_source": "http_bridge",
                    "connected": data.get("connected", r.status == 200),
                    "bridge_url": self.bridge_url,
                    "paper_trading_allowed": True,
                    "live_trading_allowed": False,
                    "preferred_mode": "paper_only",
                    "browser_bridge_last_capture_utc": bridge_snapshot.get("captured_utc"),
                    "browser_bridge_artifact_utc": _mtime_utc(self.browser_bridge_artifact),
                    "feed_artifact_utc": _mtime_utc(self.browser_feed_artifact),
                    "socket_url": bridge_snapshot.get("ws", {}).get("last_socket_url"),
                    "ws_event_count": bridge_snapshot.get("ws", {}).get("event_count"),
                    "hook_mode": bridge_snapshot.get("ws", {}).get("hook_mode"),
                    "last_stream_symbol": bridge_snapshot.get("ws", {}).get("last_stream_symbol"),
                    "visible_symbol": bridge_snapshot.get("ws", {}).get("visible_symbol"),
                    "stream_symbol_match": bridge_snapshot.get("ws", {}).get("stream_symbol_match"),
                    "current_symbol": current.get("symbol"),
                    "current_price": current.get("price"),
                    "payout_pct": current.get("payout_pct") or dom.get("payout_pct"),
                    "expiry_seconds": current.get("expiry_seconds") or dom.get("expiry_seconds"),
                    "selected_duration_label": dom.get("selected_duration_label"),
                    "duration_candidates": (dom.get("duration_candidates") or [])[:12],
                    "duration_candidates_count": len(dom.get("duration_candidates") or []),
                    "indicator_candidates": (dom.get("indicator_candidates") or [])[:20],
                    "indicator_candidates_count": len(dom.get("indicator_candidates") or []),
                    "indicator_readouts_count": len(dom.get("indicator_readouts") or []),
                    "venue_classification": due_diligence.get("brain_decision", {}).get("venue_classification"),
                    "demo_order_api_ready": command_success,
                    "demo_order_api_blocking_reason": blocking_reason,
                    "demo_order_ui_confirmation_ready": confirmation_success,
                    "demo_order_ui_confirmation_blocking_reason": confirmation_blocking_reason,
                    "last_command_status": data.get("last_command_status"),
                    "last_command_result_utc": data.get("last_command_result_utc"),
                    "recommended_usage": due_diligence.get("findings", [{}])[-1].get("assessment"),
                    "next_enablement_step": (
                        "Lane demo listo para ejecucion browser-driven en paper_only."
                        if confirmation_success else
                        ("El bridge puede hacer click, pero falta confirmar que la UI registre la operacion."
                         if command_success else
                         "Ejecutar /trading/pocket-option/demo-order-check con la pagina demo abierta y la extension recargada.")
                    ),
                }
        except Exception as e:
            return {
                "success": False,
                "provider": "pocket_option",
                "display_name": "Pocket Option",
                "error": str(e),
                "status": "disconnected",
                "data_source": "none",
                "bridge_url": self.bridge_url,
                "paper_trading_allowed": True,
                "live_trading_allowed": False,
                "preferred_mode": "paper_only",
                "browser_bridge_last_capture_utc": bridge_snapshot.get("captured_utc"),
                "browser_bridge_artifact_utc": _mtime_utc(self.browser_bridge_artifact),
                "feed_artifact_utc": _mtime_utc(self.browser_feed_artifact),
                "socket_url": bridge_snapshot.get("ws", {}).get("last_socket_url"),
                "ws_event_count": bridge_snapshot.get("ws", {}).get("event_count"),
                "hook_mode": bridge_snapshot.get("ws", {}).get("hook_mode"),
                "last_stream_symbol": bridge_snapshot.get("ws", {}).get("last_stream_symbol"),
                "visible_symbol": bridge_snapshot.get("ws", {}).get("visible_symbol"),
                "stream_symbol_match": bridge_snapshot.get("ws", {}).get("stream_symbol_match"),
                "current_symbol": current.get("symbol"),
                "current_price": current.get("price"),
                "payout_pct": current.get("payout_pct") or dom.get("payout_pct"),
                "expiry_seconds": current.get("expiry_seconds") or dom.get("expiry_seconds"),
                "selected_duration_label": dom.get("selected_duration_label"),
                "duration_candidates": (dom.get("duration_candidates") or [])[:12],
                "duration_candidates_count": len(dom.get("duration_candidates") or []),
                "indicator_candidates": (dom.get("indicator_candidates") or [])[:20],
                "indicator_candidates_count": len(dom.get("indicator_candidates") or []),
                "indicator_readouts_count": len(dom.get("indicator_readouts") or []),
                "symbols_detected": bridge_snapshot.get("symbols", [])[:12],
                "venue_classification": due_diligence.get("brain_decision", {}).get("venue_classification"),
                "demo_order_api_ready": False,
                "demo_order_api_blocking_reason": "bridge_trade_endpoint_blocked_or_bridge_down",
                "recommended_usage": due_diligence.get("findings", [{}])[-1].get("assessment"),
                "next_enablement_step": "Verificar estado del browser bridge y extension.",
            }

    async def get_balance(self) -> Dict:
        try:
            s = await self._get_session(timeout=10)
            async with s.get(f"{self.bridge_url}/balance") as r:
                data = await r.json()
                return {"success": r.status == 200, "balance": data.get("balance"), "currency": data.get("currency","USD")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_trade_history(self, limit: int = 100) -> Dict:
        try:
            s = await self._get_session(timeout=10)
            async with s.get(f"{self.bridge_url}/trades/history", params={"limit": limit}) as r:
                data = await r.json()
                trades = data.get("trades", [])
                return {"success": r.status == 200, "trades": trades, "count": len(trades)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_open_trades(self) -> Dict:
        try:
            s = await self._get_session(timeout=10)
            async with s.get(f"{self.bridge_url}/trades/open") as r:
                data = await r.json()
                return {"success": r.status == 200, "open_trades": data.get("trades",[]), "count": data.get("count",0)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def place_trade(self, symbol: str, direction: str, amount: float, duration: int) -> Dict:
        try:
            s = await self._get_session(timeout=10)
            async with s.post(
                f"{self.bridge_url}/trade",
                json={"symbol": symbol, "direction": direction, "amount": amount, "duration": duration},
            ) as r:
                data = await r.json()
                command_id = data.get("command_id")
                if r.status != 200 or not data.get("success") or not command_id:
                    return {
                        "success": False,
                        "trade_id": data.get("trade_id"),
                        "status": data.get("status"),
                        "reason": data.get("reason"),
                        "message": data.get("message"),
                        "raw": data,
                    }

                for _ in range(_PO_BROWSER_COMMAND_WAIT_SECONDS):
                    await asyncio.sleep(1)
                    async with s.get(f"{self.bridge_url}/commands/status/{command_id}") as status_response:
                        status_payload = await status_response.json()
                        command = status_payload.get("command") or {}
                        command_status = command.get("status")
                        result_payload = command.get("result") or {}
                        if command_status in {"completed", "failed"}:
                            click_submitted = bool(result_payload.get("accepted_click"))
                            ui_trade_confirmed = bool(result_payload.get("ui_trade_confirmed"))
                            return {
                                "success": ui_trade_confirmed,
                                "click_submitted": click_submitted,
                                "ui_trade_confirmed": ui_trade_confirmed,
                                "trade_id": command_id,
                                "status": command_status,
                                "reason": result_payload.get("reason"),
                                "message": result_payload.get("status"),
                                "raw": {
                                    "queued": data,
                                    "command": command,
                                },
                            }

                return {
                    "success": False,
                    "trade_id": command_id,
                    "status": "timed_out_waiting_browser_result",
                    "reason": "browser_command_timeout",
                    "message": (
                        "Bridge accepted the command but no browser result arrived before timeout. "
                        "The Pocket Option tab may be background-throttled or not polling commands fast enough."
                    ),
                    "raw": data,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
