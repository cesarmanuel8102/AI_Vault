"""
Brain Chat V9 — trading/router.py
Todos los endpoints de trading como APIRouter (no como funciones sueltas).
"""
from typing import Dict, List

from fastapi import APIRouter

from brain_v9.trading.connectors import PocketOptionBridge, QuantConnectConnector, TiingoConnector

router = APIRouter(prefix="/trading", tags=["trading"])

# Instancias lazy (no bloquean el startup)
_tiingo: TiingoConnector       = None
_qc:     QuantConnectConnector = None
_po:     PocketOptionBridge    = None


def _get_tiingo() -> TiingoConnector:
    global _tiingo
    if _tiingo is None:
        _tiingo = TiingoConnector()
    return _tiingo

def _get_qc() -> QuantConnectConnector:
    global _qc
    if _qc is None:
        _qc = QuantConnectConnector()
    return _qc

def _get_po() -> PocketOptionBridge:
    global _po
    if _po is None:
        _po = PocketOptionBridge()
    return _po


@router.get("/health")
async def trading_health() -> Dict:
    tiingo = await _get_tiingo().check_health()
    qc     = await _get_qc().check_health()
    po     = await _get_po().check_health()
    return {
        "tiingo":        tiingo,
        "quantconnect":  qc,
        "pocket_option": po,
    }


@router.get("/market/{symbol}")
async def market_data(symbol: str, source: str = "tiingo", days: int = 30) -> Dict:
    if source == "tiingo":
        return await _get_tiingo().get_historical_data(symbol, days)
    elif source == "quantconnect":
        return await _get_qc().get_historical_data(symbol, days)
    return {"success": False, "error": f"Fuente desconocida: {source}"}


@router.get("/balance")
async def balance() -> Dict:
    return await _get_po().get_balance()


@router.get("/trades/open")
async def open_trades() -> Dict:
    return await _get_po().get_open_trades()


@router.get("/trades/history")
async def trade_history(limit: int = 100) -> Dict:
    return await _get_po().get_trade_history(limit)


@router.post("/trade")
async def place_trade(symbol: str, direction: str, amount: float, duration: int) -> Dict:
    """direction: 'call' o 'put'"""
    return await _get_po().place_trade(symbol, direction, amount, duration)
