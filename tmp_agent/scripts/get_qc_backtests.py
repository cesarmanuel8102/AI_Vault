#!/usr/bin/env python3
"""
Script para obtener los últimos backtests de QuantConnect
Brain V9 - AI_VAULT
"""

import json
import os
import requests
from datetime import datetime

def load_qc_credentials():
    """Carga las credenciales de QuantConnect"""
    # Ruta por defecto
    secrets_path = os.path.join(os.path.dirname(__file__), '..', 'Secrets', 'quantconnect_access.json')
    
    # Variable de entorno alternativa
    env_path = os.environ.get('QC_SECRETS')
    if env_path:
        secrets_path = env_path
    
    try:
        with open(secrets_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo de credenciales en {secrets_path}")
        return None
    except json.JSONDecodeError:
        print(f"ERROR: Archivo de credenciales inválido en {secrets_path}")
        return None

def get_qc_backtests(credentials, limit=10):
    """Obtiene los últimos backtests de QuantConnect"""
    base_url = "https://www.quantconnect.com/api/v2"
    
    # Headers con autenticación
    headers = {
        'Authorization': f'Basic {credentials.get("api_token", "")}',
        'Content-Type': 'application/json'
    }
    
    try:
        # Primero obtenemos la lista de proyectos
        projects_url = f"{base_url}/projects/read"
        print(f"Consultando proyectos: {projects_url}")
        
        response = requests.get(projects_url, headers=headers, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"ERROR: {response.status_code} - {response.text}")
            return None
        
        projects = response.json()
        print(f"Proyectos encontrados: {len(projects.get('projects', []))}")
        
        # Para cada proyecto, obtenemos sus backtests
        all_backtests = []
        
        for project in projects.get('projects', [])[:5]:  # Limitamos a 5 proyectos
            project_id = project.get('projectId')
            project_name = project.get('name', 'Unknown')
            
            print(f"\nConsultando backtests del proyecto: {project_name} (ID: {project_id})")
            
            backtests_url = f"{base_url}/backtests/read"
            params = {
                'projectId': project_id
            }
            
            bt_response = requests.get(backtests_url, headers=headers, params=params, timeout=30)
            
            if bt_response.status_code == 200:
                backtests_data = bt_response.json()
                backtests = backtests_data.get('backtests', [])
                
                for backtest in backtests[:3]:  # Top 3 por proyecto
                    backtest['project_name'] = project_name
                    backtest['project_id'] = project_id
                    all_backtests.append(backtest)
                    
                print(f"  - {len(backtests)} backtests encontrados")
            else:
                print(f"  - ERROR obteniendo backtests: {bt_response.status_code}")
        
        # Ordenamos por fecha de creación (más recientes primero)
        all_backtests.sort(key=lambda x: x.get('created', ''), reverse=True)
        
        return all_backtests[:limit]
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR de conexión: {e}")
        return None
    except Exception as e:
        print(f"ERROR inesperado: {e}")
        return None

def format_backtest_info(backtest):
    """Formatea la información de un backtest para mostrar"""
    name = backtest.get('name', 'Sin nombre')
    project = backtest.get('project_name', 'Unknown')
    created = backtest.get('created', 'Unknown')
    backtest_id = backtest.get('backtestId', 'Unknown')
    
    # Métricas básicas si están disponibles
    statistics = backtest.get('statistics', {})
    total_return = statistics.get('Total Performance', {}).get('value', 'N/A')
    sharpe = statistics.get('Sharpe Ratio', {}).get('value', 'N/A')
    drawdown = statistics.get('Maximum Drawdown', {}).get('value', 'N/A')
    
    return f"""
{'='*60}
Backtest: {name}
Proyecto: {project}
ID: {backtest_id}
Creado: {created}
Retorno Total: {total_return}
Sharpe Ratio: {sharpe}
Max Drawdown: {drawdown}
"""

def main():
    print("=== QuantConnect Backtests Fetcher ===")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Cargar credenciales
    credentials = load_qc_credentials()
    if not credentials:
        return
    
    print(f"Credenciales cargadas exitosamente")
    
    # Obtener backtests
    backtests = get_qc_backtests(credentials, limit=10)
    
    if not backtests:
        print("No se pudieron obtener backtests")
        return
    
    print(f"\n{'='*60}")
    print(f"RESULTADOS: {len(backtests)} backtests encontrados")
    print(f"{'='*60}")
    
    for i, backtest in enumerate(backtests, 1):
        print(f"\n[{i}] {format_backtest_info(backtest)}")
    
    # Guardar resultados en JSON
    output_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'qc_backtests_latest.json')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_backtests': len(backtests),
            'backtests': backtests
        }, f, indent=2)
    
    print(f"\nResultados guardados en: {output_file}")

if __name__ == '__main__':
    main()
