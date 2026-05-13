#!/usr/bin/env python3
"""
QuantConnect Live Deployment Metrics Script
Obtiene métricas del live deployment usando la API de QuantConnect
"""

import json
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any

class QuantConnectLiveMonitor:
    def __init__(self, credentials_path: str = None):
        """Inicializa el monitor con credenciales de QuantConnect"""
        if credentials_path is None:
            credentials_path = os.environ.get('QC_SECRETS', 
                                             'C:\\AI_VAULT\\tmp_agent\\Secrets\\quantconnect_access.json')
        
        try:
            with open(credentials_path, 'r') as f:
                creds = json.load(f)
                self.user_id = creds['user_id']
                self.api_token = creds['api_token']
        except (FileNotFoundError, KeyError) as e:
            print(f"Error cargando credenciales: {e}")
            raise
        
        self.base_url = "https://www.quantconnect.com/api/v2"
        self.headers = {
            'Authorization': f'Basic {self.api_token}',
            'Content-Type': 'application/json'
        }
    
    def get_live_algorithms(self) -> Dict[str, Any]:
        """Obtiene lista de algoritmos live activos"""
        url = f"{self.base_url}/live/list"
        params = {'userId': self.user_id}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error obteniendo algoritmos live: {e}")
            return {}
    
    def get_live_performance(self, project_id: str) -> Dict[str, Any]:
        """Obtiene métricas de performance de un algoritmo live"""
        url = f"{self.base_url}/live/read"
        params = {
            'userId': self.user_id,
            'projectId': project_id
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error obteniendo performance del proyecto {project_id}: {e}")
            return {}
    
    def get_live_orders(self, project_id: str, start_date: str = None) -> Dict[str, Any]:
        """Obtiene órdenes del algoritmo live"""
        if start_date is None:
            # Por defecto, últimos 7 días
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        url = f"{self.base_url}/live/orders/read"
        params = {
            'userId': self.user_id,
            'projectId': project_id,
            'start': start_date
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error obteniendo órdenes del proyecto {project_id}: {e}")
            return {}
    
    def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas completas de todos los algoritmos live"""
        print("=== QuantConnect Live Deployment Metrics ===")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print()
        
        # Obtener algoritmos live
        live_algos = self.get_live_algorithms()
        
        if not live_algos.get('success', False):
            print("❌ Error obteniendo algoritmos live")
            return {'error': 'Failed to get live algorithms', 'response': live_algos}
        
        algorithms = live_algos.get('live', [])
        print(f"📊 Algoritmos live encontrados: {len(algorithms)}")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_algorithms': len(algorithms),
            'algorithms': []
        }
        
        for algo in algorithms:
            project_id = algo.get('projectId')
            name = algo.get('name', 'Unknown')
            status = algo.get('status', 'Unknown')
            
            print(f"\n🔍 Analizando: {name} (ID: {project_id})")
            print(f"   Status: {status}")
            
            # Obtener performance
            performance = self.get_live_performance(project_id)
            
            # Obtener órdenes recientes
            orders = self.get_live_orders(project_id)
            
            algo_metrics = {
                'project_id': project_id,
                'name': name,
                'status': status,
                'performance': performance,
                'recent_orders': orders
            }
            
            # Extraer métricas clave si están disponibles
            if performance.get('success'):
                perf_data = performance.get('live', {})
                equity = perf_data.get('equity')
                drawdown = perf_data.get('drawdown')
                trades = perf_data.get('totalTrades')
                
                print(f"   💰 Equity: {equity}")
                print(f"   📉 Drawdown: {drawdown}")
                print(f"   🔄 Total Trades: {trades}")
                
                algo_metrics['key_metrics'] = {
                    'equity': equity,
                    'drawdown': drawdown,
                    'total_trades': trades
                }
            
            results['algorithms'].append(algo_metrics)
        
        # Guardar resultados
        output_file = f"C:\\AI_VAULT\\tmp_agent\\scripts\\qc_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Resultados guardados en: {output_file}")
        return results

def main():
    """Función principal"""
    try:
        monitor = QuantConnectLiveMonitor()
        metrics = monitor.get_comprehensive_metrics()
        
        print("\n✅ Métricas obtenidas exitosamente")
        return metrics
        
    except Exception as e:
        print(f"❌ Error ejecutando el script: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}

if __name__ == "__main__":
    main()
