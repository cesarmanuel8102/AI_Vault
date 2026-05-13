#!/usr/bin/env python3
"""
Script para probar la API de QuantConnect
Creado por Brain V9 Agent
"""

import json
import requests
import os
from pathlib import Path

def load_qc_credentials():
    """Carga credenciales de QuantConnect desde archivo JSON"""
    # Primero intenta variable de entorno
    qc_secrets = os.getenv('QC_SECRETS')
    if qc_secrets:
        secrets_path = Path(qc_secrets)
    else:
        # Usa ruta por defecto
        base_path = Path(__file__).parent.parent.parent  # C:\AI_VAULT
        secrets_path = base_path / 'tmp_agent' / 'Secrets' / 'quantconnect_access.json'
    
    try:
        with open(secrets_path, 'r') as f:
            credentials = json.load(f)
        return credentials
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de credenciales en {secrets_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Archivo de credenciales malformado en {secrets_path}")
        return None

def test_qc_api():
    """Prueba conexión con la API de QuantConnect"""
    print("=== Test API QuantConnect ===")
    
    # Cargar credenciales
    creds = load_qc_credentials()
    if not creds:
        return False
    
    # Extraer datos necesarios
    user_id = creds.get('user_id') or creds.get('userId')
    api_token = creds.get('api_token') or creds.get('apiToken')
    
    if not user_id or not api_token:
        print("Error: Credenciales incompletas (necesita user_id y api_token)")
        return False
    
    print(f"Usuario: {user_id}")
    print(f"Token: {api_token[:10]}...")
    
    # URL base de la API
    base_url = "https://www.quantconnect.com/api/v2"
    
    # Headers para autenticación
    headers = {
        'Authorization': f'Basic {user_id}:{api_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        # Test 1: Obtener información de usuario
        print("\n1. Probando endpoint /authenticate...")
        auth_url = f"{base_url}/authenticate"
        response = requests.get(auth_url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Autenticación exitosa")
            print(f"Respuesta: {json.dumps(data, indent=2)}")
        else:
            print(f"✗ Error en autenticación: {response.text}")
            return False
        
        # Test 2: Listar proyectos
        print("\n2. Probando endpoint /projects/read...")
        projects_url = f"{base_url}/projects/read"
        response = requests.post(projects_url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Listado de proyectos exitoso")
            if 'projects' in data:
                print(f"Número de proyectos: {len(data['projects'])}")
                for i, project in enumerate(data['projects'][:3]):  # Solo primeros 3
                    print(f"  - {project.get('name', 'Sin nombre')} (ID: {project.get('projectId', 'N/A')})")
            else:
                print(f"Respuesta: {json.dumps(data, indent=2)}")
        else:
            print(f"✗ Error listando proyectos: {response.text}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error de conexión: {e}")
        return False
    except Exception as e:
        print(f"✗ Error inesperado: {e}")
        return False

if __name__ == "__main__":
    success = test_qc_api()
    if success:
        print("\n✓ Test de API QuantConnect completado")
    else:
        print("\n✗ Test de API QuantConnect falló")
        exit(1)
