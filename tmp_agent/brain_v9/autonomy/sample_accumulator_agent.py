"""
Brain V9 - SampleAccumulatorAgent
Agente autónomo para acumular muestras de trades en paper con sistema de APRENDIZAJE
Ejecuta trades SOLO cuando hay señales técnicas válidas y actualiza scorecards automáticamente
"""
import asyncio
import json
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Asegurar que brain_v9 está en el path
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from brain_v9.config import BASE_PATH, IBKR_HOST, IBKR_PORT, POCKETOPTION_BRIDGE_URL
    from brain_v9.agent.tools import build_standard_executor
    from brain_v9.core.state_io import read_json, write_json
except ImportError:
    # Fallback para imports directos
    import os
    BASE_PATH = Path(os.getenv("BRAIN_BASE_PATH", "C:/AI_VAULT"))
    # Función placeholder que se reemplazará en runtime
    def build_standard_executor():
        """Lazy import de ToolExecutor."""
        from brain_v9.agent.tools import ToolExecutor
        return ToolExecutor()
    from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("SampleAccumulatorAgent")


class SampleAccumulatorAgent:
    """
    Agente que ejecuta trades basado en señales técnicas y aprende de los resultados
    """
    
    # Umbrales de promoción
    MIN_SAMPLE_QUALITY = 0.30
    MIN_ENTRIES_RESOLVED = 8
    TARGET_ENTRIES = 20
    
    # Configuración de ejecución - MODO APRENDIZAJE
    CHECK_INTERVAL_MINUTES = 2   # Revisar cada 2 minutos
    MAX_TRADES_PER_SESSION = 1000  # Máximo trades por ciclo
    COOLDOWN_MINUTES = 0         # SIN COOLDOWN
    
    def __init__(self):
        self.tools = build_standard_executor()
        self.state_path = BASE_PATH / "tmp_agent" / "state" / "sample_accumulator.json"
        self.running = False
        self.last_trade_time = None
        self.session_trades_count = 0
        self._load_state()
        
    def _load_state(self):
        """Carga estado persistente."""
        state = read_json(self.state_path, {})
        if state:
            try:
                self.last_trade_time = datetime.fromisoformat(state.get('last_trade_time', datetime.now().isoformat()))
                self.session_trades_count = state.get('session_trades_count', 0)
            except Exception as e:
                log.warning(f"Error cargando estado: {e}")
                self._reset_state()
        else:
            self._reset_state()
    
    def _reset_state(self):
        """Resetea estado."""
        self.last_trade_time = datetime.now() - timedelta(hours=1)
        self.session_trades_count = 0
        self._save_state()
    
    def _save_state(self):
        """Guarda estado."""
        try:
            write_json(self.state_path, {
                'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
                'session_trades_count': self.session_trades_count,
                'updated_utc': datetime.now().isoformat()
            })
        except Exception as e:
            log.error(f"Error guardando estado: {e}")
    
    async def start(self):
        """Inicia el loop."""
        self.running = True
        # Reset session counter on new day / new startup to avoid livelock
        # when MAX_TRADES_PER_SESSION was reached in a previous run.
        if self.last_trade_time and self.last_trade_time.date() < datetime.now().date():
            log.info("New day detected — resetting session_trades_count from %d to 0",
                     self.session_trades_count)
            self.session_trades_count = 0
            self._save_state()
        log.info("=" * 60)
        log.info("SampleAccumulatorAgent - MODO APRENDIZAJE ACTIVO")
        log.info("=" * 60)
        log.info(f"Intervalo: {self.CHECK_INTERVAL_MINUTES} min | Cooldown: {self.COOLDOWN_MINUTES} min")
        log.info(f"Min sample: {self.MIN_SAMPLE_QUALITY} | Min entries: {self.MIN_ENTRIES_RESOLVED}")
        log.info("=" * 60)
        
        while self.running:
            try:
                await self._check_and_accumulate()
                await asyncio.sleep(self.CHECK_INTERVAL_MINUTES * 60)
            except Exception as e:
                log.error(f"Error en loop: {e}")
                await asyncio.sleep(300)
    
    def stop(self):
        """Detiene el agente."""
        self.running = False
        log.info("SampleAccumulatorAgent detenido")
    
    async def _check_and_accumulate(self):
        """Revisa señales y ejecuta trades con APRENDIZAJE."""
        log.info("\n" + "=" * 60)
        log.info("CICLO DE ACUMULACION - BASADO EN SEÑALES")
        log.info("=" * 60)
        
        # 1. Obtener ranking con señales
        ranking = await self._get_strategy_ranking()
        if not ranking:
            log.warning("No se pudo obtener ranking")
            return
        
        # 2. Identificar estrategias con señal válida
        candidates = self._identify_needy_strategies(ranking)
        
        if not candidates:
            log.info("No hay estrategias con señales válidas")
            self._log_needy_without_signals(ranking)
            return
        
        log.info(f"\n✓ Estrategias listas: {len(candidates)}")
        for c in candidates:
            log.info(f"  → {c['strategy_id']}: {c['signal_direction'].upper()} ({c['signal_confidence']:.2f})")
        
        # 3. Ejecutar
        if not self._can_execute_trade():
            return
        
        top_candidate = candidates[0]
        await self._execute_paper_trades(top_candidate)
    
    async def _get_strategy_ranking(self) -> Optional[Dict]:
        """Obtiene ranking y combina con señales."""
        ranking_data = None
        
        try:
            result = await self.tools.execute("get_dashboard_data", endpoint='brain/strategy-engine/ranking')
            if result.get('success'):
                ranking_data = result.get('data', {})
        except Exception as e:
            log.error(f"Error obteniendo ranking: {e}")
        
        if not ranking_data:
            try:
                ranking_path = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_ranking_latest.json"
                ranking_data = read_json(ranking_path, {}) or None
            except Exception as e:
                log.error(f"Error leyendo ranking: {e}")
                return None
        
        # Combinar con señales
        try:
            signals_path = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_signal_snapshot_latest.json"
            signals_data = read_json(signals_path, {})
            if signals_data:
                ranking_data = self._merge_signals_with_ranking(ranking_data, signals_data)
        except Exception as e:
            log.error(f"Error cargando señales: {e}")
        
        return ranking_data
    
    def _merge_signals_with_ranking(self, ranking: Dict, signals_data: Dict) -> Dict:
        """Combina señales con ranking."""
        signals = signals_data.get('items', [])
        signal_map = {}
        for signal in signals:
            key = f"{signal.get('strategy_id')}::{signal.get('symbol')}"
            signal_map[key] = signal
        
        def combine(strategy):
            if not strategy:
                return strategy
            
            strategy_id = strategy.get('strategy_id', '')
            preferred_symbol = strategy.get('preferred_symbol', '')
            key = f"{strategy_id}::{preferred_symbol}"
            signal = signal_map.get(key)
            
            if signal:
                strategy['signal_valid'] = signal.get('signal_valid', False)
                strategy['signal_direction'] = signal.get('direction', 'call')
                strategy['signal_confidence'] = signal.get('confidence', 0.0)
                strategy['execution_ready'] = signal.get('execution_ready', False)
                strategy['market_regime'] = signal.get('market_regime', 'unknown')
                strategy['entry_price'] = signal.get('entry_price', 0.0)
                strategy['signal_reasons'] = signal.get('reasons', [])
                strategy['signal_blockers'] = signal.get('blockers', [])
            else:
                strategy['signal_valid'] = False
                strategy['signal_direction'] = 'call'
                strategy['signal_confidence'] = 0.0
                strategy['execution_ready'] = False
            
            return strategy
        
        if 'top_recovery_candidate' in ranking:
            ranking['top_recovery_candidate'] = combine(ranking['top_recovery_candidate'])
        
        if 'ranked' in ranking:
            ranking['ranked'] = [combine(s) for s in ranking['ranked']]
        
        return ranking
    
    def _identify_needy_strategies(self, ranking: Dict) -> List[Dict]:
        """Identifica estrategias con muestras insuficientes Y señal válida."""
        candidates = []
        
        # Revisar top_recovery_candidate
        recovery = ranking.get('top_recovery_candidate', {})
        if recovery:
            gap = self._calculate_gap(recovery)
            if gap > 0 and self._has_valid_signal(recovery):
                candidates.append(self._build_candidate(recovery, gap))
        
        # Revisar ranked
        ranked = ranking.get('ranked', [])
        for strategy in ranked:
            gap = self._calculate_gap(strategy)
            if gap > 0 and self._has_valid_signal(strategy):
                candidates.append(self._build_candidate(strategy, gap))
        
        # Ordenar por prioridad
        candidates.sort(key=lambda x: x['priority'], reverse=True)
        return candidates
    
    def _build_candidate(self, strategy: Dict, gap: int) -> Dict:
        """Construye candidato."""
        return {
            'strategy_id': strategy.get('strategy_id'),
            'venue': strategy.get('venue', 'unknown'),
            'entries_resolved': strategy.get('entries_resolved', 0),
            'sample_quality': strategy.get('sample_quality', 0.0),
            'target_entries': self.TARGET_ENTRIES,
            'gap': gap,
            'priority': self._calculate_priority(strategy),
            'venue_ready': strategy.get('venue_ready', False),
            'paper_only': strategy.get('paper_only', True),
            'signal_valid': strategy.get('signal_valid', False),
            'signal_direction': strategy.get('signal_direction', 'call'),
            'signal_confidence': strategy.get('signal_confidence', 0.0),
            'execution_ready': strategy.get('execution_ready', False),
            'preferred_symbol': strategy.get('preferred_symbol', ''),
            'indicators': strategy.get('indicators', [])
        }
    
    def _has_valid_signal(self, strategy: Dict) -> bool:
        """Verifica señal válida."""
        if not strategy.get('signal_valid', False):
            return False
        if not strategy.get('execution_ready', False):
            return False
        # Umbral de confianza reducido a 0.5 (50%) para permitir más trades
        if strategy.get('signal_confidence', 0) < 0.5:
            return False
        if not strategy.get('venue_ready', False):
            return False
        
        blockers = strategy.get('signal_blockers', [])
        critical = ['regime_not_allowed', 'spread_too_wide', 'symbol_not_in_universe']
        for blocker in blockers:
            if blocker in critical:
                return False
        
        return True
    
    def _calculate_gap(self, strategy: Dict) -> int:
        """Calcula trades faltantes."""
        entries = strategy.get('entries_resolved', 0)
        sample_quality = strategy.get('sample_quality', 0.0)
        
        if entries < self.MIN_ENTRIES_RESOLVED or sample_quality < self.MIN_SAMPLE_QUALITY:
            return self.TARGET_ENTRIES - entries
        return 0
    
    def _calculate_priority(self, strategy: Dict) -> float:
        """Calcula prioridad."""
        entries = strategy.get('entries_resolved', 0)
        sample_quality = strategy.get('sample_quality', 0.0)
        expectancy = strategy.get('expectancy', 0.0)
        
        gap = self.TARGET_ENTRIES - entries
        expectancy_bonus = min(expectancy * 0.1, 2.0)
        sample_penalty = max(0, (self.MIN_SAMPLE_QUALITY - sample_quality) * 10)
        
        return gap + expectancy_bonus - sample_penalty
    
    def _can_execute_trade(self) -> bool:
        """Verifica cooldown."""
        if not self.last_trade_time:
            return True
        elapsed = (datetime.now() - self.last_trade_time).total_seconds() / 60
        return elapsed >= self.COOLDOWN_MINUTES
    
    async def _execute_paper_trades(self, candidate: Dict):
        """Ejecuta trades a través de paper_execution.py (unified ledger).

        P6-07: All trades now go through the unified paper_execution path
        so they share the same ledger, deferred-resolution pipeline, and
        reconciliation with the strategy engine cycle.
        """
        strategy_id = candidate['strategy_id']
        venue = candidate['venue']

        # P-OP30a: Market hours check — block IBKR when US market closed
        from brain_v9.config import is_venue_market_open
        venue_key = "ibkr" if "ibkr" in venue else "pocket_option"
        if not is_venue_market_open(venue_key):
            log.info(f"[{strategy_id}] Market closed for {venue_key} — skipping")
            return

        gap = min(candidate['gap'], self.MAX_TRADES_PER_SESSION)
        signal_direction = candidate.get('signal_direction', 'call')
        signal_confidence = candidate.get('signal_confidence', 0.0)
        indicators = candidate.get('indicators', [])
        preferred_symbol = candidate.get('preferred_symbol', 'EURUSD_otc')
        
        log.info(f"\n▶ Ejecutando: {strategy_id}")
        log.info(f"   Señal: {signal_direction.upper()} ({signal_confidence:.2f})")
        log.info(f"   Indicadores: {', '.join(indicators[:3])}")
        log.info(f"   Gap: {gap} trades | Via: paper_execution (unified)")
        
        for i in range(gap):
            if self.session_trades_count >= self.MAX_TRADES_PER_SESSION:
                log.warning(
                    "[AccumulatorSaturation] Session limit reached: %d/%d trades. "
                    "No more trades will execute until process restart or new day.",
                    self.session_trades_count,
                    self.MAX_TRADES_PER_SESSION,
                )
                break
            # P-OP25: warn when approaching session limit (>90%)
            if (
                self.session_trades_count > 0
                and self.session_trades_count % 100 == 0
                and self.session_trades_count >= self.MAX_TRADES_PER_SESSION * 0.9
            ):
                log.warning(
                    "[AccumulatorSaturation] Approaching session limit: %d/%d trades (%.0f%%)",
                    self.session_trades_count,
                    self.MAX_TRADES_PER_SESSION,
                    100.0 * self.session_trades_count / self.MAX_TRADES_PER_SESSION,
                )
            
            log.info(f"\n   Trade {i+1}/{gap}:")
            
            try:
                # P-OP28e: execute_unified_paper_trade is synchronous and can
                # block the event loop (up to 30s for PO bridge polling).
                # Run in thread executor.
                _loop = asyncio.get_running_loop()
                result = await _loop.run_in_executor(
                    None, self._execute_unified_paper_trade, candidate,
                )
                
                if result.get('success'):
                    trade = result.get('trade', {})
                    trade_result = trade.get('result', 'pending_resolution')
                    profit = trade.get('profit', 0.0)
                    log.info(f"   ✓ Recorded: {trade_result} (profit={profit:.2f})")
                    self.session_trades_count += 1
                    self.last_trade_time = datetime.now()
                    self._save_state()
                    
                    # Esperar entre trades
                    if i < gap - 1:
                        await asyncio.sleep(random.randint(5, 15))
                else:
                    error_code = result.get('error', 'Unknown')
                    log.error(f"   ✗ Error: {error_code}")
                    # P-OP28: break early on cooldown — remaining iterations
                    # would all be rejected for the same strategy+symbol
                    if error_code == 'trade_cooldown_active':
                        log.info("   ⏸ Cooldown active — stopping trade loop early")
                        break
                    
            except Exception as e:
                log.error(f"   ✗ Excepción: {e}")
        
        log.info(f"\n✓ Sesión: {self.session_trades_count} trades")

    def _execute_unified_paper_trade(self, candidate: Dict) -> Dict:
        """Route trade through paper_execution.execute_paper_trade().

        P6-07: Single execution path.  IBKR trades get immediate
        history-based resolution; non-IBKR trades are recorded as
        pending_resolution and resolved on the next strategy engine
        cycle by resolve_pending_paper_trades().  Scorecard updates
        happen automatically when the strategy engine resolves trades.
        """
        from brain_v9.trading.paper_execution import execute_paper_trade

        strategy = {
            'strategy_id': candidate['strategy_id'],
            'venue': candidate.get('venue', 'unknown'),
            'family': candidate.get('family', 'unknown'),
            'preferred_symbol': candidate.get('preferred_symbol', ''),
        }
        signal = {
            'direction': candidate.get('signal_direction', 'call'),
            'confidence': candidate.get('signal_confidence', 0.0),
            'execution_ready': True,
            'symbol': candidate.get('preferred_symbol', ''),
            'reasons': candidate.get('signal_reasons', []),
            'blockers': candidate.get('signal_blockers', []),
        }
        feature = {
            'price_available': True,
            'last': candidate.get('entry_price'),
            'mid': candidate.get('entry_price'),
        }
        return execute_paper_trade(strategy, signal, feature)
    
    def get_status(self) -> Dict:
        """Retorna estado."""
        return {
            'running': self.running,
            'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
            'session_trades_count': self.session_trades_count,
            'check_interval_minutes': self.CHECK_INTERVAL_MINUTES,
            'cooldown_minutes': self.COOLDOWN_MINUTES,
            'min_sample_quality': self.MIN_SAMPLE_QUALITY,
            'min_entries_resolved': self.MIN_ENTRIES_RESOLVED,
            'target_entries': self.TARGET_ENTRIES
        }


# Instancia global
_sample_accumulator_instance: Optional[SampleAccumulatorAgent] = None


def get_sample_accumulator() -> SampleAccumulatorAgent:
    """Obtiene singleton."""
    global _sample_accumulator_instance
    if _sample_accumulator_instance is None:
        _sample_accumulator_instance = SampleAccumulatorAgent()
    return _sample_accumulator_instance


async def start_sample_accumulator():
    """Inicia el agente."""
    accumulator = get_sample_accumulator()
    await accumulator.start()


def stop_sample_accumulator():
    """Detiene el agente."""
    global _sample_accumulator_instance
    if _sample_accumulator_instance:
        _sample_accumulator_instance.stop()
        _sample_accumulator_instance = None


# Método para logging de estrategias sin señal
def _log_needy_without_signals(self, ranking: Dict):
    """Loguea estrategias sin señal."""
    all_needy = []
    
    recovery = ranking.get('top_recovery_candidate', {})
    if recovery:
        gap = self._calculate_gap(recovery)
        if gap > 0 and not recovery.get('signal_valid', False):
            all_needy.append({
                'strategy_id': recovery.get('strategy_id'),
                'entries_resolved': recovery.get('entries_resolved', 0),
                'signal_valid': False
            })
    
    ranked = ranking.get('ranked', [])
    for strategy in ranked:
        gap = self._calculate_gap(strategy)
        if gap > 0 and not strategy.get('signal_valid', False):
            all_needy.append({
                'strategy_id': strategy.get('strategy_id'),
                'entries_resolved': strategy.get('entries_resolved', 0),
                'signal_valid': False
            })
    
    if all_needy:
        log.info(f"\n⚠ Sin señal: {len(all_needy)} estrategias")
        for n in all_needy[:3]:
            log.info(f"  - {n['strategy_id']}: {n['entries_resolved']} entries")


# Agregar método a clase
SampleAccumulatorAgent._log_needy_without_signals = _log_needy_without_signals