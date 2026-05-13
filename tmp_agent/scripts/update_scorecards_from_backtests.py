#!/usr/bin/env python3
"""
Script para procesar resultados de backtests de QuantConnect y actualizar scorecards del sistema
Creado por Brain V9 - Agente Autónomo AI_VAULT
"""

import json
import os
from datetime import datetime
from pathlib import Path
import sys

# Agregar el directorio raíz al path para importar módulos del sistema
sys.path.append('C:\\AI_VAULT')

try:
    from core.state_io import read_json, write_json
    from trading.pipeline_integrity import PIPELINE_INTEGRITY_PATH, RANKING_V2_PATH
except ImportError as e:
    print(f"Error importando módulos del sistema: {e}")
    print("Ejecutando en modo standalone...")
    
    def read_json(path):
        """Fallback para leer JSON"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def write_json(path, data):
        """Fallback para escribir JSON"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def load_backtest_results():
    """Carga los resultados de backtests generados previamente"""
    results_path = Path('C:\\AI_VAULT\\tmp_agent\\scripts\\quantconnect_backtest_results.json')
    
    if not results_path.exists():
        print(f"❌ No se encontraron resultados de backtests en {results_path}")
        return None
    
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Cargados {len(data.get('backtests', []))} backtests")
        return data
    except Exception as e:
        print(f"❌ Error cargando resultados: {e}")
        return None

def calculate_scorecard_metrics(backtest_data):
    """Calcula métricas para scorecard basado en datos de backtest"""
    metrics = {
        'strategy_name': backtest_data.get('name', 'Unknown'),
        'backtest_id': backtest_data.get('backtestId', 'N/A'),
        'created': backtest_data.get('created', ''),
        'performance': {},
        'risk': {},
        'quality': {},
        'last_updated': datetime.now().isoformat()
    }
    
    # Extraer métricas de rendimiento
    stats = backtest_data.get('statistics', {})
    
    # Performance metrics
    metrics['performance'] = {
        'total_return': float(stats.get('Total Return', 0)),
        'annual_return': float(stats.get('Annual Return', 0)),
        'sharpe_ratio': float(stats.get('Sharpe Ratio', 0)),
        'sortino_ratio': float(stats.get('Sortino Ratio', 0)),
        'alpha': float(stats.get('Alpha', 0)),
        'beta': float(stats.get('Beta', 0))
    }
    
    # Risk metrics
    metrics['risk'] = {
        'max_drawdown': abs(float(stats.get('Maximum Drawdown', 0))),
        'volatility': float(stats.get('Annual Standard Deviation', 0)),
        'var_95': float(stats.get('Value at Risk (1%)', 0)),
        'downside_deviation': float(stats.get('Downside Deviation', 0))
    }
    
    # Quality metrics
    metrics['quality'] = {
        'win_rate': float(stats.get('Win Rate', 0)),
        'profit_loss_ratio': float(stats.get('Profit-Loss Ratio', 0)),
        'total_trades': int(stats.get('Total Trades', 0)),
        'information_ratio': float(stats.get('Information Ratio', 0))
    }
    
    # Calcular score general (0-100)
    score_components = [
        min(metrics['performance']['sharpe_ratio'] * 20, 25),  # Max 25 puntos
        max(0, 25 - metrics['risk']['max_drawdown'] * 100),    # Max 25 puntos
        metrics['quality']['win_rate'] * 25,                   # Max 25 puntos
        min(metrics['performance']['annual_return'] * 100, 25) # Max 25 puntos
    ]
    
    metrics['overall_score'] = max(0, min(100, sum(score_components)))
    
    return metrics

def update_strategy_scorecards(backtest_results):
    """Actualiza las scorecards de estrategias con los resultados de backtests"""
    scorecards_path = Path('C:\\AI_VAULT\\state\\strategy_engine\\strategy_scorecards.json')
    
    # Cargar scorecards existentes o crear estructura nueva
    if scorecards_path.exists():
        try:
            scorecards = read_json(scorecards_path)
        except:
            scorecards = {'strategies': {}, 'last_updated': ''}
    else:
        scorecards = {'strategies': {}, 'last_updated': ''}
        # Crear directorio si no existe
        scorecards_path.parent.mkdir(parents=True, exist_ok=True)
    
    updated_count = 0
    
    for backtest in backtest_results.get('backtests', []):
        try:
            metrics = calculate_scorecard_metrics(backtest)
            strategy_key = f"qc_{backtest.get('backtestId', 'unknown')}"
            
            scorecards['strategies'][strategy_key] = metrics
            updated_count += 1
            
            print(f"✅ Actualizada scorecard para {metrics['strategy_name']} (Score: {metrics['overall_score']:.1f})")
            
        except Exception as e:
            print(f"❌ Error procesando backtest {backtest.get('name', 'Unknown')}: {e}")
    
    # Actualizar timestamp
    scorecards['last_updated'] = datetime.now().isoformat()
    scorecards['total_strategies'] = len(scorecards['strategies'])
    
    # Guardar scorecards actualizadas
    try:
        write_json(scorecards_path, scorecards)
        print(f"✅ Scorecards guardadas en {scorecards_path}")
        return updated_count
    except Exception as e:
        print(f"❌ Error guardando scorecards: {e}")
        return 0

def update_pipeline_integrity():
    """Actualiza el archivo de integridad del pipeline"""
    try:
        if PIPELINE_INTEGRITY_PATH.exists():
            integrity_data = read_json(PIPELINE_INTEGRITY_PATH)
        else:
            integrity_data = {'components': {}, 'last_check': ''}
        
        # Actualizar componente de scorecards
        integrity_data['components']['scorecards'] = {
            'status': 'updated',
            'last_update': datetime.now().isoformat(),
            'source': 'quantconnect_backtests'
        }
        
        integrity_data['last_check'] = datetime.now().isoformat()
        
        PIPELINE_INTEGRITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_json(PIPELINE_INTEGRITY_PATH, integrity_data)
        
        print(f"✅ Pipeline integrity actualizada en {PIPELINE_INTEGRITY_PATH}")
        
    except Exception as e:
        print(f"❌ Error actualizando pipeline integrity: {e}")

def generate_summary_report(updated_count, scorecards_path):
    """Genera un reporte resumen de la actualización"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'operation': 'scorecard_update_from_backtests',
        'strategies_updated': updated_count,
        'scorecards_file': str(scorecards_path),
        'status': 'completed' if updated_count > 0 else 'no_updates'
    }
    
    report_path = Path('C:\\AI_VAULT\\tmp_agent\\scripts\\scorecard_update_report.json')
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"📊 Reporte generado en {report_path}")
    except Exception as e:
        print(f"❌ Error generando reporte: {e}")
    
    return report

def main():
    """Función principal del script"""
    print("🚀 Iniciando actualización de scorecards desde backtests de QuantConnect...")
    print("=" * 70)
    
    # 1. Cargar resultados de backtests
    backtest_results = load_backtest_results()
    if not backtest_results:
        print("❌ No se pudieron cargar los resultados de backtests")
        return 1
    
    # 2. Actualizar scorecards
    updated_count = update_strategy_scorecards(backtest_results)
    
    # 3. Actualizar pipeline integrity
    update_pipeline_integrity()
    
    # 4. Generar reporte
    scorecards_path = Path('C:\\AI_VAULT\\state\\strategy_engine\\strategy_scorecards.json')
    report = generate_summary_report(updated_count, scorecards_path)
    
    print("=" * 70)
    print(f"✅ Proceso completado. Estrategias actualizadas: {updated_count}")
    print(f"📁 Scorecards: {scorecards_path}")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
