"""
Brain Chat V9 — trading/connectors.py
TiingoConnector, QuantConnectConnector, PocketOptionBridge
Extraído de V8.0 líneas 2973-3417.
Corrección: paths de secrets desde config.py en lugar de hardcoded.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from aiohttp import ClientSession, ClientTimeout

from brain_v9.config import SECRETS


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
                return {"success": r.status == 200, "status_code": r.status}
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
        import hashlib, hmac, time
        ts  = str(int(time.time()))
        sig = hmac.new(
            self.token.encode(), f"{self.user_id}:{ts}".encode(), hashlib.sha256
        ).hexdigest()
        return {
            "Authorization": f"Basic {self.user_id}:{sig}",
            "Timestamp":     ts,
            "Content-Type":  "application/json",
        }

    async def check_health(self) -> Dict:
        try:
            s = await self._get_session()
            async with s.get(f"{self.BASE_URL}/authenticate", headers=self._headers()) as r:
                return {"success": r.status == 200, "status_code": r.status}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_historical_data(self, symbol: str, days: int = 30) -> Dict:
        try:
            s = await self._get_session()
            async with s.get(
                f"{self.BASE_URL}/data/read",
                headers=self._headers(),
                params={"symbol": symbol, "resolution": "Daily", "count": days},
            ) as r:
                if r.status != 200:
                    return {"success": False, "error": f"HTTP {r.status}"}
                return {"success": True, "data": await r.json(), "symbol": symbol}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# PocketOption Bridge
# ─────────────────────────────────────────────────────────────────────────────
class PocketOptionBridge(_SessionMixin):
    def __init__(self, bridge_url: str = "http://127.0.0.1:8765"):
        self.logger     = logging.getLogger("PocketOptionBridge")
        self.bridge_url = bridge_url

    async def check_health(self) -> Dict:
        try:
            s = await self._get_session(timeout=10)
            async with s.get(f"{self.bridge_url}/health") as r:
                data = await r.json()
                return {"success": r.status == 200, "status": data.get("status"), "connected": data.get("connected", False)}
        except Exception as e:
            return {"success": False, "error": str(e), "status": "disconnected"}

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
                return {"success": r.status == 200 and data.get("success"), "trade_id": data.get("trade_id"), "status": data.get("status")}
        except Exception as e:
            return {"success": False, "error": str(e)}
