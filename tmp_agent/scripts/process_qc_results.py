#!/usr/bin/env python3
"""
Brain V9 - QC Results Processor
Procesa resultados de backtests de QuantConnect y actualiza scorecards
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add AI_VAULT to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from trading.qc_bridge import ingest_qc_results
except ImportError:
    print("Error: No se pudo importar ingest_qc_results desde trading.qc_bridge")
    print("Verificar que el módulo existe en C:\\AI_VAULT\\trading\\")
    sys.exit(1)

def load_qc_results(results_file="qc_backtest_results.json"):
    """
    Carga resultados de backtests desde archivo JSON
    """
    results_path = Path(__file__).parent / results_file
    
    if not results_path.exists():
        print(f"Error: Archivo de resultados no encontrado: {results_path}")
        return None
    
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✓ Cargados resultados desde {results_path}")
        return data
    except Exception as e:
        print(f"Error cargando resultados: {e}")
        return None

def process_backtest_result(backtest_data):
    """
    Procesa un resultado de backtest individual
    Convierte formato QC a formato esperado por ingest_qc_results
    """
    try:
        # Extraer métricas principales
        result = {
            'backtest_id': backtest_data.get('backtestId', 'unknown'),
            'name': backtest_data.get('name', 'Unnamed Strategy'),
            'created': backtest_data.get('created', datetime.now().isoformat()),
            'completed': backtest_data.get('completed', datetime.now().isoformat()),
            'progress': backtest_data.get('progress', 1.0),
            'result': backtest_data.get('result', 'RuntimeError'),
            
            # Métricas de performance
            'statistics': {
                'total_performance': backtest_data.get('statistics', {}).get('Total Performance', {}),
                'rolling_performance': backtest_data.get('statistics', {}).get('Rolling Performance', {}),
                'summary': backtest_data.get('statistics', {}).get('Summary', {})
            },
            
            # Información adicional
            'runtime_statistics': backtest_data.get('runtimeStatistics', {}),
            'rolling_window': backtest_data.get('rollingWindow', {})
        }
        
        return result
    except Exception as e:
        print(f"Error procesando backtest {backtest_data.get('backtestId', 'unknown')}: {e}")
        return None

def main():
    """
    Función principal: carga resultados y los ingesta
    """
    print("=== Brain V9 - QC Results Processor ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # 1. Cargar resultados de QC
    print("[1/3] Cargando resultados de QuantConnect...")
    qc_data = load_qc_results()
    
    if not qc_data:
        print("❌ No se pudieron cargar los resultados")
        return False
    
    # 2. Procesar cada backtest
    print("[2/3] Procesando backtests...")
    processed_results = []
    
    backtests = qc_data.get('backtests', [])
    if not backtests:
        print("⚠️  No se encontraron backtests en los datos")
        return False
    
    for i, backtest in enumerate(backtests, 1):
        print(f"  Procesando backtest {i}/{len(backtests)}: {backtest.get('name', 'Unnamed')}")
        
        processed = process_backtest_result(backtest)
        if processed:
            processed_results.append(processed)
        
    print(f"✓ Procesados {len(processed_results)} backtests")
    
    # 3. Ingestar resultados usando ingest_qc_results
    print("[3/3] Actualizando scorecards...")
    
    try:
        # Llamar a ingest_qc_results con los datos procesados
        success_count = 0
        
        for result in processed_results:
            try:
                # ingest_qc_results espera datos en formato específico
                ingestion_result = ingest_qc_results(result)
                
                if ingestion_result:
                    success_count += 1
                    print(f"  ✓ Ingested: {result['name']}")
                else:
                    print(f"  ❌ Failed: {result['name']}")
                    
            except Exception as e:
                print(f"  ❌ Error ingesting {result['name']}: {e}")
        
        print(f"\n=== RESUMEN ===")
        print(f"Backtests procesados: {len(processed_results)}")
        print(f"Scorecards actualizados: {success_count}")
        print(f"Errores: {len(processed_results) - success_count}")
        
        if success_count > 0:
            print("\n✅ Proceso completado exitosamente")
            return True
        else:
            print("\n❌ No se actualizó ningún scorecard")
            return False
            
    except Exception as e:
        print(f"❌ Error en ingesta: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
