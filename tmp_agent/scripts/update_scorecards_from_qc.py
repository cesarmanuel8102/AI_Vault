#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para procesar resultados de backtests de QuantConnect y actualizar scorecards
Brain V9 - AI_VAULT Ecosystem
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add AI_VAULT to path
sys.path.insert(0, 'C:\\AI_VAULT')

try:
    from core.state_io import read_json_state, write_json_state
    from trading.pipeline_integrity import RANKING_V2_PATH, PIPELINE_INTEGRITY_PATH
except ImportError as e:
    print(f"Error importing AI_VAULT modules: {e}")
    sys.exit(1)

def load_qc_results(results_file="C:\\AI_VAULT\\tmp_agent\\data\\qc_backtests_results.json"):
    """Carga los resultados de backtests de QuantConnect"""
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Archivo de resultados no encontrado: {results_file}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        return None

def process_backtest_results(qc_data):
    """Procesa los datos de backtests y extrae métricas relevantes"""
    processed_results = []
    
    if not qc_data or 'backtests' not in qc_data:
        return processed_results
    
    for backtest in qc_data['backtests']:
        try:
            # Extraer métricas clave
            result = {
                'backtest_id': backtest.get('backtestId', 'unknown'),
                'name': backtest.get('name', 'Unnamed Strategy'),
                'created': backtest.get('created', ''),
                'completed': backtest.get('completed', ''),
                'progress': backtest.get('progress', 0),
                'result': backtest.get('result', 'Unknown'),
                'error': backtest.get('error', ''),
                'statistics': {}
            }
            
            # Procesar estadísticas si están disponibles
            if 'statistics' in backtest:
                stats = backtest['statistics']
                result['statistics'] = {
                    'total_trades': stats.get('Total Trades', 0),
                    'win_rate': stats.get('Win Rate', 0),
                    'profit_loss_ratio': stats.get('Profit-Loss Ratio', 0),
                    'total_return': stats.get('Total Return', 0),
                    'annual_return': stats.get('Annual Return', 0),
                    'max_drawdown': stats.get('Maximum Drawdown', 0),
                    'sharpe_ratio': stats.get('Sharpe Ratio', 0),
                    'sortino_ratio': stats.get('Sortino Ratio', 0),
                    'treynor_ratio': stats.get('Treynor Ratio', 0),
                    'information_ratio': stats.get('Information Ratio', 0)
                }
            
            processed_results.append(result)
            
        except Exception as e:
            print(f"Error procesando backtest {backtest.get('backtestId', 'unknown')}: {e}")
            continue
    
    return processed_results

def update_strategy_scorecards(processed_results):
    """Actualiza los scorecards de estrategias con los resultados de QC"""
    try:
        # Leer scorecards actuales
        current_scorecards = read_json_state('strategy_scorecards_latest.json', default={})
        
        # Timestamp para la actualización
        update_timestamp = datetime.now().isoformat()
        
        # Procesar cada resultado
        for result in processed_results:
            strategy_name = result['name']
            backtest_id = result['backtest_id']
            
            # Crear o actualizar scorecard para esta estrategia
            if strategy_name not in current_scorecards:
                current_scorecards[strategy_name] = {
                    'strategy_name': strategy_name,
                    'source': 'quantconnect',
                    'created': update_timestamp,
                    'last_updated': update_timestamp,
                    'backtests': {},
                    'performance_summary': {
                        'total_backtests': 0,
                        'successful_backtests': 0,
                        'avg_return': 0,
                        'avg_sharpe': 0,
                        'avg_max_drawdown': 0,
                        'best_backtest': None,
                        'worst_backtest': None
                    }
                }
            
            # Actualizar información del backtest específico
            current_scorecards[strategy_name]['backtests'][backtest_id] = {
                'backtest_id': backtest_id,
                'created': result['created'],
                'completed': result['completed'],
                'progress': result['progress'],
                'result': result['result'],
                'error': result['error'],
                'statistics': result['statistics'],
                'updated': update_timestamp
            }
            
            # Actualizar timestamp de la estrategia
            current_scorecards[strategy_name]['last_updated'] = update_timestamp
            
            # Recalcular resumen de performance
            update_performance_summary(current_scorecards[strategy_name])
        
        # Guardar scorecards actualizados
        success = write_json_state('strategy_scorecards_latest.json', current_scorecards)
        
        if success:
            print(f"✓ Scorecards actualizados exitosamente para {len(processed_results)} backtests")
            print(f"✓ Estrategias procesadas: {list(set([r['name'] for r in processed_results]))}")
            return True
        else:
            print("✗ Error guardando scorecards actualizados")
            return False
            
    except Exception as e:
        print(f"Error actualizando scorecards: {e}")
        return False

def update_performance_summary(strategy_scorecard):
    """Actualiza el resumen de performance de una estrategia"""
    backtests = strategy_scorecard['backtests']
    
    if not backtests:
        return
    
    # Filtrar backtests completados exitosamente
    completed_backtests = [
        bt for bt in backtests.values() 
        if bt['progress'] == 1.0 and bt['result'] != 'RuntimeError' and not bt['error']
    ]
    
    summary = strategy_scorecard['performance_summary']
    summary['total_backtests'] = len(backtests)
    summary['successful_backtests'] = len(completed_backtests)
    
    if completed_backtests:
        # Calcular promedios
        returns = [bt['statistics'].get('total_return', 0) for bt in completed_backtests]
        sharpes = [bt['statistics'].get('sharpe_ratio', 0) for bt in completed_backtests]
        drawdowns = [bt['statistics'].get('max_drawdown', 0) for bt in completed_backtests]
        
        summary['avg_return'] = sum(returns) / len(returns) if returns else 0
        summary['avg_sharpe'] = sum(sharpes) / len(sharpes) if sharpes else 0
        summary['avg_max_drawdown'] = sum(drawdowns) / len(drawdowns) if drawdowns else 0
        
        # Encontrar mejor y peor backtest
        if returns:
            best_idx = returns.index(max(returns))
            worst_idx = returns.index(min(returns))
            
            summary['best_backtest'] = {
                'backtest_id': completed_backtests[best_idx]['backtest_id'],
                'return': returns[best_idx],
                'sharpe': sharpes[best_idx] if best_idx < len(sharpes) else 0
            }
            
            summary['worst_backtest'] = {
                'backtest_id': completed_backtests[worst_idx]['backtest_id'],
                'return': returns[worst_idx],
                'sharpe': sharpes[worst_idx] if worst_idx < len(sharpes) else 0
            }

def update_pipeline_integrity():
    """Actualiza el pipeline integrity con información de QuantConnect"""
    try:
        # Leer pipeline integrity actual
        current_integrity = read_json_state('pipeline_integrity_latest.json', default={})
        
        # Agregar información de QuantConnect
        if 'data_sources' not in current_integrity:
            current_integrity['data_sources'] = {}
        
        current_integrity['data_sources']['quantconnect'] = {
            'status': 'active',
            'last_update': datetime.now().isoformat(),
            'type': 'backtest_results',
            'description': 'QuantConnect backtests integration via API'
        }
        
        # Guardar
        success = write_json_state('pipeline_integrity_latest.json', current_integrity)
        
        if success:
            print("✓ Pipeline integrity actualizado con información de QuantConnect")
        else:
            print("✗ Error actualizando pipeline integrity")
            
        return success
        
    except Exception as e:
        print(f"Error actualizando pipeline integrity: {e}")
        return False

def main():
    """Función principal"""
    print("=== Actualizador de Scorecards desde QuantConnect ===")
    print(f"Iniciando procesamiento: {datetime.now()}")
    
    # 1. Cargar resultados de QuantConnect
    print("\n1. Cargando resultados de backtests...")
    qc_data = load_qc_results()
    
    if not qc_data:
        print("✗ No se pudieron cargar los resultados de QuantConnect")
        print("   Ejecuta primero: python get_qc_backtests.py")
        return False
    
    print(f"✓ Cargados {len(qc_data.get('backtests', []))} backtests")
    
    # 2. Procesar resultados
    print("\n2. Procesando resultados...")
    processed_results = process_backtest_results(qc_data)
    
    if not processed_results:
        print("✗ No se pudieron procesar los resultados")
        return False
    
    print(f"✓ Procesados {len(processed_results)} backtests")
    
    # 3. Actualizar scorecards
    print("\n3. Actualizando scorecards...")
    scorecard_success = update_strategy_scorecards(processed_results)
    
    # 4. Actualizar pipeline integrity
    print("\n4. Actualizando pipeline integrity...")
    integrity_success = update_pipeline_integrity()
    
    # Resumen final
    print("\n=== RESUMEN ===")
    if scorecard_success and integrity_success:
        print("✓ Actualización completada exitosamente")
        print(f"✓ Scorecards actualizados para {len(set([r['name'] for r in processed_results]))} estrategias")
        print(f"✓ {len(processed_results)} backtests procesados")
        return True
    else:
        print("✗ Algunos errores durante la actualización")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
