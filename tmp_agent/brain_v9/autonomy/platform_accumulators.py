"""
Brain V9 - SampleAccumulator separados por plataforma
Cada plataforma tiene su propio acumulador con U independiente
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum

from brain_v9.config import BASE_PATH
from brain_v9.trading.platform_manager import get_platform_manager
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("PlatformAccumulators")

STATE_PATH = BASE_PATH / "tmp_agent" / "state" / "platform_accumulators"
STATE_PATH.mkdir(parents=True, exist_ok=True)

class Platform(Enum):
    POCKET_OPTION = "pocket_option"
    IBKR = "ibkr"
    INTERNAL = "internal_paper"

class PlatformSampleAccumulator:
    """
    Acumulador de muestras específico para una plataforma
    Cada plataforma tiene su propio U score y métricas independientes
    """
    
    def __init__(self, platform: Platform):
        self.platform = platform
        self.platform_name = platform.value
        self.state_path = STATE_PATH / f"{self.platform_name}_accumulator.json"
        
        # Configuración específica por plataforma
        if platform == Platform.POCKET_OPTION:
            self.min_sample_quality = 0.20  # Más permisivo para PO
            self.min_entries = 5
            self.check_interval = 1  # minutos - más frecuente
            self.symbols = ["EURUSD_otc", "USDCHF_otc", "GBPUSD_otc", "AUDNZD_otc"]
        elif platform == Platform.IBKR:
            self.min_sample_quality = 0.30  # Más estricto para IBKR
            self.min_entries = 8
            self.check_interval = 5  # minutos
            self.symbols = ["SPY", "AAPL", "QQQ", "TSLA"]
        else:
            self.min_sample_quality = 0.25
            self.min_entries = 5
            self.check_interval = 2
            self.symbols = ["EURUSD_otc", "SPY"]
        
        self.running = False
        self.session_trades = 0
        self.last_trade_time = None
        self.consecutive_skips = 0
        
        # Referencia al platform manager para U independiente
        self.platform_manager = get_platform_manager()
        
        self._load_state()
    
    def _load_state(self):
        """Carga estado persistente"""
        state = read_json(self.state_path, {})
        if state:
            try:
                self.session_trades = state.get('session_trades', 0)
                self.consecutive_skips = state.get('consecutive_skips', 0)
                last_time = state.get('last_trade_time')
                if last_time:
                    self.last_trade_time = datetime.fromisoformat(last_time)
                # P-OP27: Daily reset — if state was last updated on a
                # different UTC day, reset session_trades so the 20-trade
                # cap doesn't carry over forever.
                updated_str = state.get('updated_utc')
                if updated_str:
                    try:
                        updated_dt = datetime.fromisoformat(updated_str)
                        if updated_dt.date() < datetime.utcnow().date():
                            log.info(f"[{self.platform_name}] Daily reset: session_trades {self.session_trades} -> 0")
                            self.session_trades = 0
                            self.consecutive_skips = 0
                            self._save_state()
                    except (ValueError, TypeError) as exc:
                        log.debug(f"[{self.platform_name}] Could not parse updated_utc for daily reset: {exc}")
            except Exception as e:
                log.warning(f"[{self.platform_name}] Error cargando estado: {e}")
                self._reset_state()
        else:
            self._reset_state()
    
    def _reset_state(self):
        """Resetea estado"""
        self.session_trades = 0
        self.consecutive_skips = 0
        self.last_trade_time = datetime.now() - timedelta(hours=1)
        self._save_state()
    
    def _save_state(self):
        """Guarda estado"""
        try:
            write_json(self.state_path, {
                'platform': self.platform_name,
                'session_trades': self.session_trades,
                'consecutive_skips': self.consecutive_skips,
                'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
                'updated_utc': datetime.now().isoformat()
            })
        except Exception as e:
            log.error(f"[{self.platform_name}] Error guardando estado: {e}")
    
    async def start(self):
        """Inicia el loop de acumulación para esta plataforma"""
        self.running = True
        log.info(f"=" * 60)
        log.info(f"[{self.platform_name.upper()}] Platform Accumulator iniciado")
        log.info(f"=" * 60)
        log.info(f"Min sample: {self.min_sample_quality} | Min entries: {self.min_entries}")
        log.info(f"Check interval: {self.check_interval} min")
        log.info(f"Symbols: {', '.join(self.symbols)}")
        log.info(f"=" * 60)
        
        while self.running:
            try:
                await self._check_and_accumulate()
                await asyncio.sleep(self.check_interval * 60)
            except Exception as e:
                log.error(f"[{self.platform_name}] Error en loop: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        """Detiene el acumulador"""
        self.running = False
        log.info(f"[{self.platform_name}] Acumulador detenido")
    
    async def _check_and_accumulate(self):
        """Revisa señales y ejecuta trades para esta plataforma"""
        log.info(f"\n[{self.platform_name}] {'='*50}")
        log.info(f"[{self.platform_name}] CICLO DE ACUMULACIÓN")
        log.info(f"[{self.platform_name}] {'='*50}")
        
        # 1. Obtener señales de esta plataforma
        signals = await self._get_platform_signals()
        
        if not signals:
            log.info(f"[{self.platform_name}] No hay señales disponibles")
            self._increment_skip("No signals")
            return
        
        # 2. Filtrar señales válidas
        valid_signals = self._filter_valid_signals(signals)
        
        if not valid_signals:
            log.info(f"[{self.platform_name}] No hay señales válidas")
            self._increment_skip("No valid signals")
            return
        
        log.info(f"[{self.platform_name}] Señales válidas: {len(valid_signals)}")
        for sig in valid_signals[:3]:  # Mostrar top 3
            log.info(f"  → {sig['strategy_id']}: {sig.get('direction', 'N/A').upper()} "
                    f"(conf: {sig.get('confidence', 0):.2f})")
        
        # 3. Verificar si podemos ejecutar
        if not self._can_execute():
            return
        
        # 4. Seleccionar mejor señal
        top_signal = valid_signals[0]
        
        # 5. Ejecutar trade
        await self._execute_trade(top_signal)
    
    async def _get_platform_signals(self) -> List[Dict]:
        """Obtiene señales específicas de esta plataforma"""
        try:
            # Leer snapshot de señales
            signals_path = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_signal_snapshot_latest.json"
            
            data = read_json(signals_path, {})
            
            # Filtrar por plataforma
            platform_signals = [
                item for item in data.get('items', [])
                if item.get('venue') == self.platform_name
            ]
            
            return platform_signals
            
        except Exception as e:
            log.error(f"[{self.platform_name}] Error obteniendo señales: {e}")
            return []
    
    def _filter_valid_signals(self, signals: List[Dict]) -> List[Dict]:
        """Filtra señales válidas para esta plataforma"""
        valid = []
        
        for signal in signals:
            # P-OP30b: Respect signal engine's execution_ready flag.
            # This incorporates session blocking, confidence thresholds,
            # indicator checks, etc.  Previously the accumulator bypassed
            # all of these and only checked confidence >= 0.45.
            if not signal.get('execution_ready', False):
                continue

            # Verificar requisitos básicos
            if not signal.get('price_available'):
                continue
            
            # P-OP27: Lowered from 0.6 to 0.45, then aligned to 0.48 to match
            # strategy engine confidence clamp range [0.48, 0.68] (P-OP32n).
            # The previous 0.6 cutoff filtered out most valid signals the engine produces.
            if signal.get('confidence', 0) < 0.48:
                continue
            
            # Para PO: verificar payout
            if self.platform == Platform.POCKET_OPTION:
                payout = signal.get('payout_pct', 0)
                if payout < 35:  # Mínimo 35% payout
                    continue
            
            # Para IBKR: verificar spread
            if self.platform == Platform.IBKR:
                spread = signal.get('spread_pct', 1)
                if spread > 0.01:  # Máximo 1% spread
                    continue
            
            valid.append(signal)
        
        # Ordenar por confianza
        valid.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        return valid
    
    def _can_execute(self) -> bool:
        """Verifica si se puede ejecutar un trade"""
        # P-OP30a: Market hours check — block IBKR when US market closed
        from brain_v9.config import is_venue_market_open
        venue_key = "ibkr" if self.platform == Platform.IBKR else "pocket_option"
        if not is_venue_market_open(venue_key):
            log.info(f"[{self.platform_name}] Market closed for {venue_key} — skipping")
            return False

        # Verificar cooldown
        if self.last_trade_time:
            elapsed = (datetime.now() - self.last_trade_time).total_seconds() / 60
            if elapsed < 1:  # Mínimo 1 minuto entre trades
                return False
        
        # Verificar límites de sesión
        if self.session_trades >= 1000:  # Máximo 1000 trades por día UTC
            log.info(f"[{self.platform_name}] Límite de trades alcanzado ({self.session_trades}/1000)")
            return False
        
        return True
    
    async def _execute_trade(self, signal: Dict):
        """Ejecuta un trade delegando al paper execution engine.

        No fabrica resultados — el trade se registra como pending_resolution
        y se resuelve en el siguiente ciclo del strategy engine cuando haya
        nuevos datos de precio (deferred forward resolution).
        """
        try:
            from brain_v9.trading.paper_execution import execute_paper_trade

            strategy_id = signal.get('strategy_id', 'unknown')
            symbol = signal.get('symbol', 'unknown')
            direction = signal.get('direction', 'call')
            confidence = signal.get('confidence', 0.5)
            
            log.info(f"[{self.platform_name}] EJECUTANDO TRADE")
            log.info(f"[{self.platform_name}]   Strategy: {strategy_id}")
            log.info(f"[{self.platform_name}]   Symbol: {symbol}")
            log.info(f"[{self.platform_name}]   Direction: {direction.upper()}")
            log.info(f"[{self.platform_name}]   Confidence: {confidence:.2f}")
            
            # P-OP28e: execute_paper_trade is synchronous and can block the event
            # loop for up to 30 seconds when venue is pocket_option (sync HTTP
            # polling to the bridge).  Run it in a thread executor.
            import asyncio as _asyncio
            import functools as _ft

            _loop = _asyncio.get_running_loop()
            trade_result = await _loop.run_in_executor(
                None,
                _ft.partial(
                    execute_paper_trade,
                    strategy={
                        "strategy_id": strategy_id,
                        "family": "trend_following",
                        "venue": self.platform_name,
                        "preferred_symbol": symbol,
                    },
                    signal={
                        "direction": direction,
                        "confidence": confidence,
                        "symbol": symbol,
                        "execution_ready": True,
                        "feature_key": signal.get("feature_key"),
                        # P-OP27: Pass duration so paper_execution dispatches
                        # with the correct holding period (300s for PO).
                        "duration_seconds": 300 if self.platform == Platform.POCKET_OPTION else None,
                        # P-OP31d: Pass session metadata so ledger entries
                        # record the correct session_name instead of None.
                        "hour_utc": signal.get("hour_utc"),
                        "session_name": signal.get("session_name"),
                        "session_quality": signal.get("session_quality"),
                        # P-OP32d: Pass indicator values for ledger capture
                        "rsi_14": signal.get("rsi_14"),
                        "bb_pct_b": signal.get("bb_pct_b"),
                        "stoch_k": signal.get("stoch_k"),
                        "stoch_d": signal.get("stoch_d"),
                        "macd_histogram": signal.get("macd_histogram"),
                        "indicator_confluence": signal.get("indicator_confluence"),
                        "market_regime": signal.get("market_regime"),
                        "price_zscore": signal.get("price_zscore"),
                        "window_change_pct": signal.get("window_change_pct"),
                    },
                    feature={
                        "last": signal.get("entry_price"),
                        "mid": signal.get("entry_price"),
                        "price_available": signal.get("price_available", True),
                        "last_vs_close_pct": signal.get("last_vs_close_pct", 0.0),
                        "bid_ask_imbalance": signal.get("bid_ask_imbalance", 0.0),
                        "payout_pct": signal.get("payout_pct", 80.0),
                    },
                ),
            )

            outcome = trade_result.get("result", "pending_resolution")
            profit = trade_result.get("profit", 0.0)
            
            # Actualizar estado
            self.session_trades += 1
            self.last_trade_time = datetime.now()
            self.consecutive_skips = 0
            self._save_state()
            
            # NOTE: Platform metrics are recorded when the trade resolves
            # via _update_platform_metrics() in paper_execution.py.
            # Recording here with pending_resolution/profit=0 would
            # double-count once the trade resolves.
            
            log.info(f"[{self.platform_name}] TRADE REGISTRADO")
            log.info(f"[{self.platform_name}]   Result: {outcome.upper()}")
            log.info(f"[{self.platform_name}]   Profit: {profit:+.2f}")
            
            # Actualizar scorecard
            await self._update_scorecard(strategy_id, symbol, direction, outcome, profit)
            
        except Exception as e:
            log.error(f"[{self.platform_name}] Error ejecutando trade: {e}")
    
    async def _update_scorecard(self, strategy_id: str, symbol: str, direction: str, result: str, profit: float):
        """Actualiza el scorecard de la estrategia con el trade ejecutado."""
        try:
            from brain_v9.trading.strategy_scorecard import update_strategy_scorecard

            trade = {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "direction": direction,
                "venue": self.platform_name,
                "result": result,
                "profit": profit,
                "timestamp": datetime.now().isoformat(),
                "resolved": result not in ("pending", "pending_resolution"),
            }

            scorecard_update = update_strategy_scorecard(
                strategy={"strategy_id": strategy_id, "venue": self.platform_name},
                trade=trade,
            )

            agg = scorecard_update.get("aggregate", {})
            log.info(
                f"[{self.platform_name}] Scorecard actualizado para {strategy_id}: "
                f"entries_resolved={agg.get('entries_resolved', 0)}, "
                f"net_pnl={agg.get('net_pnl', 0)}"
            )
        except Exception as e:
            log.error(f"[{self.platform_name}] Error actualizando scorecard: {e}")
    
    def _increment_skip(self, reason: str):
        """Incrementa contador de skips"""
        self.consecutive_skips += 1
        self._save_state()
        
        log.info(f"[{self.platform_name}] Skip #{self.consecutive_skips}: {reason}")
        
        # Actualizar U con skip — fixed: constant -0.05 delta per skip,
        # NOT escalating -0.05 * consecutive_skips (which was a bug causing
        # u_score to plummet to -72 in hours)
        self.platform_manager.update_platform_u(
            self.platform_name,
            -0.05,  # Fixed constant penalty per skip
            f"Skip: {reason}"
        )

class MultiPlatformAccumulator:
    """Gestiona múltiples acumuladores de plataforma"""
    
    def __init__(self):
        self.accumulators: Dict[Platform, PlatformSampleAccumulator] = {}
        self._init_accumulators()
    
    def _init_accumulators(self):
        """Inicializa acumuladores para cada plataforma"""
        for platform in Platform:
            self.accumulators[platform] = PlatformSampleAccumulator(platform)
    
    async def start_all(self):
        """Inicia todos los acumuladores en paralelo"""
        tasks = []
        for accumulator in self.accumulators.values():
            task = asyncio.create_task(accumulator.start())
            tasks.append(task)
        
        log.info("=" * 60)
        log.info("MULTI-PLATFORM ACCUMULATOR iniciado")
        log.info("=" * 60)
        log.info(f"Plataformas activas: {len(self.accumulators)}")
        for platform in self.accumulators.keys():
            log.info(f"  • {platform.value}")
        log.info("=" * 60)
        
        await asyncio.gather(*tasks)
    
    def stop_all(self):
        """Detiene todos los acumuladores"""
        for accumulator in self.accumulators.values():
            accumulator.stop()
        log.info("Multi-Platform Accumulator detenido")
    
    def get_platform_status(self, platform: Platform) -> Dict:
        """Obtiene estado de una plataforma específica"""
        if platform in self.accumulators:
            acc = self.accumulators[platform]
            return {
                'platform': platform.value,
                'running': acc.running,
                'session_trades': acc.session_trades,
                'consecutive_skips': acc.consecutive_skips,
                'last_trade': acc.last_trade_time.isoformat() if acc.last_trade_time else None
            }
        return {}
    
    def get_all_status(self) -> Dict[str, Any]:
        """Obtiene estado de todas las plataformas"""
        return {
            platform.value: self.get_platform_status(platform)
            for platform in self.accumulators.keys()
        }

# Instancia global
_multi_platform_accumulator: Optional[MultiPlatformAccumulator] = None

def get_multi_platform_accumulator() -> MultiPlatformAccumulator:
    """Obtiene instancia singleton"""
    global _multi_platform_accumulator
    if _multi_platform_accumulator is None:
        _multi_platform_accumulator = MultiPlatformAccumulator()
    return _multi_platform_accumulator
