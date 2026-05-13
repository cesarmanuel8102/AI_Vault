#!/usr/bin/env python3
"""
QuantConnect API - Historial de Backtests
Script para obtener el historial completo de backtests desde QuantConnect
"""

import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

class QuantConnectAPI:
    def __init__(self):
        self.base_url = "https://www.quantconnect.com/api/v2"
        self.credentials = self._load_credentials()
        self.session = requests.Session()
        
    def _load_credentials(self) -> Dict[str, str]:
        """Carga credenciales desde archivo o variables de entorno"""
        # Intentar cargar desde archivo
        secrets_path = os.environ.get('QC_SECRETS', 'C:\\AI_VAULT\\tmp_agent\\Secrets\\quantconnect_access.json')
        
        if os.path.exists(secrets_path):
            try:
                with open(secrets_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error cargando credenciales desde {secrets_path}: {e}")
        
        # Fallback a variables de entorno
        return {
            'user_id': os.environ.get('QC_USER_ID', ''),
            'api_token': os.environ.get('QC_API_TOKEN', '')
        }
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: Dict = None) -> Dict:
        """Realiza petición autenticada a la API"""
        url = f"{self.base_url}/{endpoint}"
        
        # Autenticación básica con user_id y api_token
        auth = (self.credentials['user_id'], self.credentials['api_token'])
        
        try:
            if method == 'GET':
                response = self.session.get(url, auth=auth, params=params or {})
            elif method == 'POST':
                response = self.session.post(url, auth=auth, json=params or {})
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error en petición a {url}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Status: {e.response.status_code}")
                print(f"Response: {e.response.text}")
            return {'success': False, 'error': str(e)}
    
    def get_projects(self) -> List[Dict]:
        """Obtiene lista de proyectos"""
        print("Obteniendo lista de proyectos...")
        result = self._make_request('projects/read')
        
        if result.get('success', True):
            projects = result.get('projects', [])
            print(f"Encontrados {len(projects)} proyectos")
            return projects
        else:
            print(f"Error obteniendo proyectos: {result.get('error', 'Unknown')}")
            return []
    
    def get_backtests(self, project_id: int) -> List[Dict]:
        """Obtiene backtests de un proyecto específico"""
        print(f"Obteniendo backtests del proyecto {project_id}...")
        result = self._make_request(f'backtests/{project_id}/read')
        
        if result.get('success', True):
            backtests = result.get('backtests', [])
            print(f"Encontrados {len(backtests)} backtests en proyecto {project_id}")
            return backtests
        else:
            print(f"Error obteniendo backtests del proyecto {project_id}: {result.get('error', 'Unknown')}")
            return []
    
    def get_backtest_details(self, project_id: int, backtest_id: str) -> Dict:
        """Obtiene detalles completos de un backtest"""
        print(f"Obteniendo detalles del backtest {backtest_id}...")
        result = self._make_request(f'backtests/{project_id}/{backtest_id}/read')
        
        if result.get('success', True):
            return result
        else:
            print(f"Error obteniendo detalles del backtest {backtest_id}: {result.get('error', 'Unknown')}")
            return {}
    
    def get_complete_backtest_history(self, limit_projects: Optional[int] = None) -> Dict:
        """Obtiene historial completo de backtests de todos los proyectos"""
        print("=== INICIANDO OBTENCIÓN DE HISTORIAL COMPLETO DE BACKTESTS ===")
        
        # Verificar credenciales
        if not self.credentials.get('user_id') or not self.credentials.get('api_token'):
            return {
                'success': False,
                'error': 'Credenciales incompletas. Verificar user_id y api_token.',
                'credentials_found': bool(self.credentials.get('user_id') and self.credentials.get('api_token'))
            }
        
        history = {
            'timestamp': datetime.now().isoformat(),
            'projects': [],
            'total_backtests': 0,
            'summary': {}
        }
        
        # Obtener proyectos
        projects = self.get_projects()
        if limit_projects:
            projects = projects[:limit_projects]
        
        # Para cada proyecto, obtener sus backtests
        for project in projects:
            project_id = project.get('projectId')
            project_name = project.get('name', f'Project_{project_id}')
            
            print(f"\n--- Procesando proyecto: {project_name} (ID: {project_id}) ---")
            
            project_data = {
                'project_id': project_id,
                'project_name': project_name,
                'project_info': project,
                'backtests': []
            }
            
            # Obtener backtests del proyecto
            backtests = self.get_backtests(project_id)
            
            for backtest in backtests:
                backtest_id = backtest.get('backtestId')
                backtest_name = backtest.get('name', f'Backtest_{backtest_id}')
                
                print(f"  • {backtest_name} (ID: {backtest_id})")
                
                # Obtener detalles completos del backtest
                details = self.get_backtest_details(project_id, backtest_id)
                
                backtest_data = {
                    'backtest_id': backtest_id,
                    'backtest_name': backtest_name,
                    'basic_info': backtest,
                    'detailed_info': details
                }
                
                project_data['backtests'].append(backtest_data)
            
            history['projects'].append(project_data)
            history['total_backtests'] += len(backtests)
        
        # Generar resumen
        history['summary'] = {
            'total_projects': len(history['projects']),
            'total_backtests': history['total_backtests'],
            'projects_with_backtests': len([p for p in history['projects'] if p['backtests']]),
            'average_backtests_per_project': history['total_backtests'] / max(len(history['projects']), 1)
        }
        
        print(f"\n=== RESUMEN FINAL ===")
        print(f"Proyectos procesados: {history['summary']['total_projects']}")
        print(f"Total de backtests: {history['summary']['total_backtests']}")
        print(f"Proyectos con backtests: {history['summary']['projects_with_backtests']}")
        
        return history
    
    def save_history_to_file(self, history: Dict, filename: str = None) -> str:
        """Guarda el historial en un archivo JSON"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"C:\\AI_VAULT\\tmp_agent\\data\\quantconnect_backtest_history_{timestamp}.json"
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"\nHistorial guardado en: {filename}")
            return filename
        except Exception as e:
            print(f"Error guardando historial: {e}")
            return ""

def main():
    """Función principal"""
    print("QuantConnect - Obtención de Historial de Backtests")
    print("=" * 50)
    
    # Crear instancia del cliente API
    qc_api = QuantConnectAPI()
    
    # Obtener historial completo
    # Limitar a 5 proyectos para prueba inicial
    history = qc_api.get_complete_backtest_history(limit_projects=5)
    
    if history.get('success') == False:
        print(f"\nERROR: {history.get('error')}")
        print(f"Credenciales encontradas: {history.get('credentials_found', False)}")
        return
    
    # Guardar en archivo
    filename = qc_api.save_history_to_file(history)
    
    # Mostrar resumen en consola
    if history.get('summary'):
        print("\n" + "="*50)
        print("RESUMEN DEL HISTORIAL OBTENIDO:")
        print(f"• Total de proyectos: {history['summary']['total_projects']}")
        print(f"• Total de backtests: {history['summary']['total_backtests']}")
        print(f"• Proyectos con backtests: {history['summary']['projects_with_backtests']}")
        print(f"• Promedio backtests/proyecto: {history['summary']['average_backtests_per_project']:.1f}")
        
        if filename:
            print(f"• Archivo guardado: {filename}")
    
    print("\nProceso completado.")

if __name__ == "__main__":
    main()
