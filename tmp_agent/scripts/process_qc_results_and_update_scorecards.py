#!/usr/bin/env python3
"""
Brain V9 - QC Results Processor & Scorecard Updater
Procesa resultados de backtests de QuantConnect y actualiza scorecards
"""

import sys
import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    from config import QC_SECRETS
    from trading.hypothesis_engine import ingest_qc_results
except ImportError as e:
    print(f"Error importando módulos: {e}")
    sys.exit(1)

class QCResultsProcessor:
    def __init__(self):
        self.qc_credentials = self._load_qc_credentials()
        self.base_url = "https://www.quantconnect.com/api/v2"
        
    def _load_qc_credentials(self):
        """Carga credenciales de QuantConnect"""
        try:
            with open(QC_SECRETS, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error cargando credenciales QC: {e}")
            return None
    
    def get_recent_backtests(self, days_back=7, limit=20):
        """Obtiene backtests recientes de QC"""
        if not self.qc_credentials:
            print("No hay credenciales disponibles")
            return []
            
        headers = {
            'Authorization': f'Basic {self.qc_credentials.get("token", "")}'
        }
        
        # Fecha límite
        since_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        url = f"{self.base_url}/backtests/read"
        params = {
            'start': 0,
            'length': limit,
            'projectId': self.qc_credentials.get('project_id', ''),
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            backtests = data.get('backtests', [])
            
            # Filtrar por fecha
            recent_backtests = []
            for bt in backtests:
                bt_date = bt.get('created', '')
                if bt_date >= since_date:
                    recent_backtests.append(bt)
                    
            return recent_backtests
            
        except Exception as e:
            print(f"Error obteniendo backtests: {e}")
            return []
    
    def get_backtest_details(self, backtest_id):
        """Obtiene detalles específicos de un backtest"""
        if not self.qc_credentials:
            return None
            
        headers = {
            'Authorization': f'Basic {self.qc_credentials.get("token", "")}'
        }
        
        url = f"{self.base_url}/backtests/read"
        params = {
            'backtestId': backtest_id,
            'projectId': self.qc_credentials.get('project_id', '')
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error obteniendo detalles del backtest {backtest_id}: {e}")
            return None
    
    def extract_scorecard_data(self, backtest_data):
        """Extrae datos relevantes para scorecard de un backtest"""
        if not backtest_data:
            return None
            
        # Estructura básica para scorecard
        scorecard_data = {
            'backtest_id': backtest_data.get('backtestId', ''),
            'name': backtest_data.get('name', ''),
            'created': backtest_data.get('created', ''),
            'completed': backtest_data.get('completed', ''),
            'success': backtest_data.get('success', False),
            'error': backtest_data.get('error', ''),
            'progress': backtest_data.get('progress', 0),
            
            # Métricas de rendimiento
            'statistics': {},
            'charts': {},
            'orders': [],
            'runtime_statistics': {}
        }
        
        # Extraer estadísticas si están disponibles
        result = backtest_data.get('result', {})
        if result:
            scorecard_data['statistics'] = result.get('Statistics', {})
            scorecard_data['charts'] = result.get('Charts', {})
            scorecard_data['orders'] = result.get('Orders', [])
            scorecard_data['runtime_statistics'] = result.get('RuntimeStatistics', {})
        
        return scorecard_data
    
    def process_and_update_scorecards(self, days_back=7):
        """Procesa backtests recientes y actualiza scorecards"""
        print(f"Procesando backtests de los últimos {days_back} días...")
        
        # Obtener backtests recientes
        backtests = self.get_recent_backtests(days_back)
        
        if not backtests:
            print("No se encontraron backtests recientes")
            return
            
        print(f"Encontrados {len(backtests)} backtests recientes")
        
        processed_results = []
        
        for bt in backtests:
            print(f"\nProcesando backtest: {bt.get('name', 'Sin nombre')}")
            print(f"ID: {bt.get('backtestId', 'N/A')}")
            print(f"Estado: {bt.get('progress', 0)}% - {'Exitoso' if bt.get('success') else 'Fallido/En progreso'}")
            
            # Obtener detalles completos
            details = self.get_backtest_details(bt.get('backtestId'))
            if details:
                scorecard_data = self.extract_scorecard_data(details)
                if scorecard_data:
                    processed_results.append(scorecard_data)
                    
        if processed_results:
            print(f"\n=== ACTUALIZANDO SCORECARDS ===")
            print(f"Procesando {len(processed_results)} resultados...")
            
            try:
                # Llamar a la función ingest_qc_results para actualizar scorecards
                result = ingest_qc_results(processed_results)
                print(f"Resultado de ingesta: {result}")
                
                print("✅ Scorecards actualizados exitosamente")
                
            except Exception as e:
                print(f"❌ Error actualizando scorecards: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("No hay resultados para procesar")

def main():
    """Función principal"""
    processor = QCResultsProcessor()
    
    # Procesar backtests de los últimos 7 días por defecto
    days_back = 7
    if len(sys.argv) > 1:
        try:
            days_back = int(sys.argv[1])
        except ValueError:
            print("Argumento inválido para días. Usando 7 días por defecto.")
    
    processor.process_and_update_scorecards(days_back)

if __name__ == "__main__":
    main()
