#!/usr/bin/env python3
"""
Script de Ingesta y Actualización de Scorecards
Procesa resultados de backtests de QuantConnect y actualiza scorecards del sistema
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path

# Agregar AI_VAULT al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from trading.qc_bridge import QuantConnectBridge
    from core.state_io import StateIO
    from config import Config
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from AI_VAULT directory")
    sys.exit(1)

def main():
    """Función principal de ingesta y actualización"""
    print("=== Script de Ingesta y Actualización de Scorecards ===")
    print(f"Inicio: {datetime.now()}")
    
    try:
        # 1. Conectar a QuantConnect y obtener últimos backtests
        print("\n1. Conectando a QuantConnect...")
        qc_bridge = QuantConnectBridge()
        
        # Obtener últimos backtests (últimos 10)
        backtests = qc_bridge.get_recent_backtests(limit=10)
        print(f"Obtenidos {len(backtests)} backtests recientes")
        
        # 2. Procesar cada backtest
        processed_results = []
        for backtest in backtests:
            print(f"\nProcesando backtest: {backtest.get('name', 'Unknown')}")
            
            # Extraer métricas relevantes
            result = {
                'backtest_id': backtest.get('backtestId'),
                'name': backtest.get('name'),
                'created': backtest.get('created'),
                'completed': backtest.get('completed'),
                'success': backtest.get('success', False),
                'statistics': backtest.get('statistics', {}),
                'runtime_statistics': backtest.get('runtimeStatistics', {}),
                'rolling_window': backtest.get('rollingWindow', {})
            }
            
            # Calcular métricas derivadas
            stats = result['statistics']
            if stats:
                result['sharpe_ratio'] = stats.get('Sharpe Ratio', 0)
                result['total_return'] = stats.get('Total Return', 0)
                result['max_drawdown'] = stats.get('Drawdown', 0)
                result['win_rate'] = stats.get('Win Rate', 0)
                result['profit_loss_ratio'] = stats.get('Profit-Loss Ratio', 0)
            
            processed_results.append(result)
        
        # 3. Guardar resultados procesados
        results_file = Path("C:/AI_VAULT/tmp_agent/data/processed_backtests.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(results_file, 'w') as f:
            json.dump(processed_results, f, indent=2, default=str)
        
        print(f"\nResultados guardados en: {results_file}")
        
        # 4. Usar ingest_qc_results para actualizar scorecards
        print("\n4. Actualizando scorecards del sistema...")
        
        # Simular la llamada a ingest_qc_results
        # (En el sistema real, esto sería una llamada a la herramienta)
        update_summary = {
            'processed_backtests': len(processed_results),
            'successful_backtests': sum(1 for r in processed_results if r['success']),
            'avg_sharpe_ratio': sum(r.get('sharpe_ratio', 0) for r in processed_results) / len(processed_results) if processed_results else 0,
            'avg_total_return': sum(r.get('total_return', 0) for r in processed_results) / len(processed_results) if processed_results else 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Guardar resumen de actualización
        summary_file = Path("C:/AI_VAULT/tmp_agent/data/scorecard_update_summary.json")
        with open(summary_file, 'w') as f:
            json.dump(update_summary, f, indent=2)
        
        print(f"Resumen de actualización guardado en: {summary_file}")
        
        # 5. Mostrar resumen final
        print("\n=== RESUMEN DE INGESTA ===")
        print(f"Backtests procesados: {update_summary['processed_backtests']}")
        print(f"Backtests exitosos: {update_summary['successful_backtests']}")
        print(f"Sharpe Ratio promedio: {update_summary['avg_sharpe_ratio']:.4f}")
        print(f"Retorno total promedio: {update_summary['avg_total_return']:.4f}")
        print(f"Completado: {datetime.now()}")
        
        return True
        
    except Exception as e:
        print(f"\nError durante la ingesta: {e}")
        print(f"Tipo de error: {type(e).__name__}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
