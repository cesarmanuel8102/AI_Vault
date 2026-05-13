#!/usr/bin/env python3
"""
Script para obtener el último backtest de QuantConnect
Creado por Brain V9 - Agente Autónomo
"""

import json
import requests
import os
from datetime import datetime

def load_qc_credentials():
    """Carga las credenciales de QuantConnect"""
    # Primero intenta la variable de entorno
    secrets_path = os.environ.get('QC_SECRETS')
    
    # Si no existe, usa la ruta por defecto
    if not secrets_path:
        secrets_path = r'C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json'
    
    try:
        with open(secrets_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de credenciales en {secrets_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: El archivo de credenciales no es un JSON válido")
        return None

def get_latest_backtest(credentials):
    """Obtiene el último backtest de QuantConnect"""
    if not credentials:
        return None
    
    # URL base de la API de QuantConnect
    base_url = "https://www.quantconnect.com/api/v2"
    
    # Headers para autenticación
    headers = {
        'Authorization': f"Basic {credentials.get('api_token', '')}",
        'Content-Type': 'application/json'
    }
    
    try:
        # Obtener lista de proyectos
        projects_url = f"{base_url}/projects/read"
        projects_response = requests.get(projects_url, headers=headers)
        
        if projects_response.status_code != 200:
            print(f"Error al obtener proyectos: {projects_response.status_code}")
            print(f"Respuesta: {projects_response.text}")
            return None
        
        projects = projects_response.json()
        print(f"Proyectos encontrados: {len(projects.get('projects', []))}")
        
        if not projects.get('projects'):
            print("No se encontraron proyectos")
            return None
        
        # Tomar el primer proyecto (o buscar uno específico)
        project_id = projects['projects'][0]['projectId']
        print(f"Usando proyecto ID: {project_id}")
        
        # Obtener backtests del proyecto
        backtests_url = f"{base_url}/backtests/read"
        backtests_params = {'projectId': project_id}
        
        backtests_response = requests.get(backtests_url, headers=headers, params=backtests_params)
        
        if backtests_response.status_code != 200:
            print(f"Error al obtener backtests: {backtests_response.status_code}")
            print(f"Respuesta: {backtests_response.text}")
            return None
        
        backtests = backtests_response.json()
        print(f"Backtests encontrados: {len(backtests.get('backtests', []))}")
        
        if not backtests.get('backtests'):
            print("No se encontraron backtests")
            return None
        
        # Obtener el último backtest (más reciente)
        latest_backtest = sorted(
            backtests['backtests'], 
            key=lambda x: x.get('created', ''), 
            reverse=True
        )[0]
        
        print("\n=== ÚLTIMO BACKTEST ===")
        print(f"ID: {latest_backtest.get('backtestId')}")
        print(f"Nombre: {latest_backtest.get('name')}")
        print(f"Creado: {latest_backtest.get('created')}")
        print(f"Estado: {latest_backtest.get('status')}")
        print(f"Progreso: {latest_backtest.get('progress', 0)}%")
        
        # Si está completado, obtener resultados detallados
        if latest_backtest.get('status') == 'Completed':
            backtest_id = latest_backtest['backtestId']
            results_url = f"{base_url}/backtests/read"
            results_params = {'projectId': project_id, 'backtestId': backtest_id}
            
            results_response = requests.get(results_url, headers=headers, params=results_params)
            
            if results_response.status_code == 200:
                results = results_response.json()
                print("\n=== RESULTADOS ===")
                
                # Extraer métricas principales si están disponibles
                if 'statistics' in results:
                    stats = results['statistics']
                    print(f"Total Return: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('TotalReturn', 'N/A')}")
                    print(f"Sharpe Ratio: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('SharpeRatio', 'N/A')}")
                    print(f"Max Drawdown: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('Drawdown', 'N/A')}")
                
                return results
            else:
                print(f"Error al obtener resultados detallados: {results_response.status_code}")
        
        return latest_backtest
        
    except requests.exceptions.RequestException as e:
        print(f"Error de conexión: {e}")
        return None
    except Exception as e:
        print(f"Error inesperado: {e}")
        return None

def main():
    print("=== QuantConnect - Último Backtest ===")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Cargar credenciales
    credentials = load_qc_credentials()
    if not credentials:
        print("No se pudieron cargar las credenciales")
        return
    
    print("Credenciales cargadas exitosamente")
    
    # Obtener último backtest
    result = get_latest_backtest(credentials)
    
    if result:
        print("\n=== OPERACIÓN EXITOSA ===")
        print("Último backtest obtenido correctamente")
    else:
        print("\n=== ERROR ===")
        print("No se pudo obtener el último backtest")

if __name__ == "__main__":
    main()
