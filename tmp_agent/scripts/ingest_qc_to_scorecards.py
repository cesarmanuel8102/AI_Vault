#!/usr/bin/env python3
"""
Script de Ingestión QC → Scorecards
Procesa resultados de backtests de QuantConnect y actualiza scorecards correspondientes

Brain V9 - AI_VAULT Ecosystem
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Agregar AI_VAULT al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.state_io import read_json_file, write_json_file
from trading.pipeline_integrity import get_strategy_scorecards, update_strategy_scorecard

class QCResultsIngestor:
    """Ingesta y procesa resultados de QuantConnect para actualizar scorecards"""
    
    def __init__(self):
        self.base_path = Path("C:/AI_VAULT")
        self.tmp_path = self.base_path / "tmp_agent"
        self.state_path = self.base_path / "state"
        self.qc_results_file = self.tmp_path / "qc_backtests_latest.json"
        
    def load_qc_results(self) -> Optional[Dict]:
        """Carga los resultados más recientes de QC"""
        if not self.qc_results_file.exists():
            print(f"❌ No se encontró archivo de resultados QC: {self.qc_results_file}")
            return None
            
        try:
            data = read_json_file(str(self.qc_results_file))
            print(f"✅ Cargados {len(data.get('backtests', []))} backtests de QC")
            return data
        except Exception as e:
            print(f"❌ Error cargando resultados QC: {e}")
            return None
    
    def extract_performance_metrics(self, backtest: Dict) -> Dict:
        """Extrae métricas de performance de un backtest QC"""
        stats = backtest.get('statistics', {})
        
        # Mapeo de métricas QC a formato scorecard
        metrics = {
            'total_return': self._safe_float(stats.get('Total Performance', {}).get('value')),
            'sharpe_ratio': self._safe_float(stats.get('Sharpe Ratio', {}).get('value')),
            'max_drawdown': self._safe_float(stats.get('Maximum Drawdown', {}).get('value')),
            'win_rate': self._safe_float(stats.get('Win Rate', {}).get('value')),
            'profit_loss_ratio': self._safe_float(stats.get('Profit-Loss Ratio', {}).get('value')),
            'total_trades': self._safe_int(stats.get('Total Trades', {}).get('value')),
            'annual_return': self._safe_float(stats.get('Annual Return', {}).get('value')),
            'annual_volatility': self._safe_float(stats.get('Annual Standard Deviation', {}).get('value')),
            'information_ratio': self._safe_float(stats.get('Information Ratio', {}).get('value')),
            'tracking_error': self._safe_float(stats.get('Tracking Error', {}).get('value'))
        }
        
        return {k: v for k, v in metrics.items() if v is not None}
    
    def _safe_float(self, value) -> Optional[float]:
        """Conversión segura a float"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                # Remover % y convertir
                value = value.replace('%', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value) -> Optional[int]:
        """Conversión segura a int"""
        if value is None:
            return None
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return None
    
    def map_qc_to_strategy(self, backtest: Dict) -> Optional[str]:
        """Mapea un backtest QC a una estrategia del sistema"""
        name = backtest.get('name', '').lower()
        
        # Mapeo básico por nombre
        strategy_mapping = {
            'rsi': 'rsi_divergence',
            'macd': 'macd_crossover', 
            'bollinger': 'bollinger_bands',
            'sma': 'sma_crossover',
            'ema': 'ema_crossover',
            'momentum': 'momentum_strategy',
            'mean_reversion': 'mean_reversion',
            'breakout': 'breakout_strategy'
        }
        
        for key, strategy in strategy_mapping.items():
            if key in name:
                return strategy
        
        # Si no hay mapeo, usar el nombre directamente (limpio)
        clean_name = ''.join(c for c in name if c.isalnum() or c == '_').lower()
        return clean_name if clean_name else 'unknown_strategy'
    
    def update_scorecard_with_qc_data(self, strategy_name: str, backtest: Dict) -> bool:
        """Actualiza scorecard de una estrategia con datos de QC"""
        try:
            # Obtener scorecard actual
            scorecards = get_strategy_scorecards()
            if strategy_name not in scorecards:
                print(f"⚠️  Estrategia {strategy_name} no encontrada, creando nueva scorecard")
                scorecards[strategy_name] = {
                    'strategy_name': strategy_name,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'performance_metrics': {},
                    'qc_backtests': [],
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }
            
            scorecard = scorecards[strategy_name]
            
            # Extraer métricas de performance
            metrics = self.extract_performance_metrics(backtest)
            
            # Actualizar métricas en scorecard
            if 'performance_metrics' not in scorecard:
                scorecard['performance_metrics'] = {}
            
            scorecard['performance_metrics'].update({
                'qc_total_return': metrics.get('total_return'),
                'qc_sharpe_ratio': metrics.get('sharpe_ratio'),
                'qc_max_drawdown': metrics.get('max_drawdown'),
                'qc_win_rate': metrics.get('win_rate'),
                'qc_total_trades': metrics.get('total_trades'),
                'qc_annual_return': metrics.get('annual_return'),
                'qc_volatility': metrics.get('annual_volatility')
            })
            
            # Agregar backtest a historial
            if 'qc_backtests' not in scorecard:
                scorecard['qc_backtests'] = []
            
            backtest_record = {
                'backtest_id': backtest.get('backtestId'),
                'name': backtest.get('name'),
                'created': backtest.get('created'),
                'completed': backtest.get('completed'),
                'metrics': metrics,
                'ingested_at': datetime.now(timezone.utc).isoformat()
            }
            
            scorecard['qc_backtests'].append(backtest_record)
            scorecard['last_updated'] = datetime.now(timezone.utc).isoformat()
            
            # Guardar scorecard actualizada
            update_strategy_scorecard(strategy_name, scorecard)
            
            print(f"✅ Scorecard de {strategy_name} actualizada con datos QC")
            return True
            
        except Exception as e:
            print(f"❌ Error actualizando scorecard {strategy_name}: {e}")
            return False
    
    def process_all_backtests(self) -> Dict[str, Any]:
        """Procesa todos los backtests y actualiza scorecards"""
        results = {
            'processed': 0,
            'updated': 0,
            'errors': 0,
            'strategies_updated': [],
            'processing_timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Cargar resultados QC
        qc_data = self.load_qc_results()
        if not qc_data:
            results['error'] = 'No se pudieron cargar resultados QC'
            return results
        
        backtests = qc_data.get('backtests', [])
        results['processed'] = len(backtests)
        
        print(f"🔄 Procesando {len(backtests)} backtests...")
        
        for backtest in backtests:
            try:
                # Mapear a estrategia
                strategy_name = self.map_qc_to_strategy(backtest)
                
                if self.update_scorecard_with_qc_data(strategy_name, backtest):
                    results['updated'] += 1
                    if strategy_name not in results['strategies_updated']:
                        results['strategies_updated'].append(strategy_name)
                else:
                    results['errors'] += 1
                    
            except Exception as e:
                print(f"❌ Error procesando backtest {backtest.get('name', 'unknown')}: {e}")
                results['errors'] += 1
        
        return results
    
    def generate_ingestion_report(self, results: Dict) -> str:
        """Genera reporte de ingestión"""
        report = f"""
=== REPORTE DE INGESTIÓN QC → SCORECARDS ===
Timestamp: {results['processing_timestamp']}

RESUMEN:
- Backtests procesados: {results['processed']}
- Scorecards actualizadas: {results['updated']}
- Errores: {results['errors']}

ESTRATEGIAS ACTUALIZADAS:
"""
        
        for strategy in results.get('strategies_updated', []):
            report += f"- {strategy}\n"
        
        if results.get('error'):
            report += f"\nERROR PRINCIPAL: {results['error']}\n"
        
        return report

def main():
    """Función principal"""
    print("🚀 Iniciando ingestión QC → Scorecards...")
    
    ingestor = QCResultsIngestor()
    results = ingestor.process_all_backtests()
    
    # Generar reporte
    report = ingestor.generate_ingestion_report(results)
    print(report)
    
    # Guardar reporte
    report_file = ingestor.tmp_path / f"ingestion_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"📄 Reporte guardado en: {report_file}")
    
    return results

if __name__ == "__main__":
    try:
        results = main()
        print(f"\n✅ Ingestión completada. Scorecards actualizadas: {results['updated']}")
    except Exception as e:
        print(f"❌ Error en ingestión: {e}")
        sys.exit(1)
