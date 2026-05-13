#!/usr/bin/env python3
"""
QuantConnect Backtest Fetcher
Script para obtener backtests usando la API de QuantConnect
"""

import json
import os
import requests
from datetime import datetime

def load_credentials():
    """Carga credenciales de QuantConnect"""
    secrets_path = r'C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json'
    
    # Verificar variable de entorno alternativa
    if 'QC_SECRETS' in os.environ:
        secrets_path = os.environ['QC_SECRETS']
    
    try:
        with open(secrets_path, 'r') as f:
            creds = json.load(f)
        return creds
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de credenciales en {secrets_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Formato JSON inválido en {secrets_path}")
        return None

def get_backtests(user_id, api_token, project_id=None, limit=10):
    """Obtiene backtests de QuantConnect"""
    base_url = "https://www.quantconnect.com/api/v2"
    
    # Endpoint para obtener backtests
    if project_id:
        url = f"{base_url}/backtests/read"
        params = {
            'projectId': project_id,
            'start': 0,
            'end': limit
        }
    else:
        # Obtener proyectos primero
        url = f"{base_url}/projects/read"
        params = {
            'start': 0,
            'end': limit
        }
    
    headers = {
        'Authorization': f'Basic {user_id}:{api_token}'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error en la petición a QuantConnect: {e}")
        return None

def main():
    """Función principal"""
    print("=== QuantConnect Backtest Fetcher ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Cargar credenciales
    creds = load_credentials()
    if not creds:
        return
    
    user_id = creds.get('user_id') or creds.get('userId')
    api_token = creds.get('api_token') or creds.get('apiToken')
    
    if not user_id or not api_token:
        print("Error: Credenciales incompletas (user_id y api_token requeridos)")
        return
    
    print(f"Usuario: {user_id[:8]}...")
    
    # Primero obtener proyectos
    print("\n1. Obteniendo proyectos...")
    projects_data = get_backtests(user_id, api_token)
    
    if not projects_data:
        print("Error al obtener proyectos")
        return
    
    print(f"Respuesta de proyectos: {json.dumps(projects_data, indent=2)}")
    
    # Si hay proyectos, obtener backtests del primero
    if 'projects' in projects_data and projects_data['projects']:
        project = projects_data['projects'][0]
        project_id = project['projectId']
        print(f"\n2. Obteniendo backtests del proyecto {project_id}...")
        
        backtests_data = get_backtests(user_id, api_token, project_id)
        if backtests_data:
            print(f"Backtests: {json.dumps(backtests_data, indent=2)}")
        else:
            print("Error al obtener backtests")
    else:
        print("No se encontraron proyectos")

if __name__ == "__main__":
    main()
