#!/usr/bin/env python3
"""
Script para ejecutar ingest_qc_results con credenciales de QuantConnect
Creado automáticamente por Brain V9 Agent
"""

import os
import sys
import json
from pathlib import Path

# Agregar el directorio raíz al path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trading.qc_bridge import ingest_qc_results
from config import QC_SECRETS

def main():
    """Ejecuta ingest_qc_results con las credenciales configuradas"""
    
    print("🔄 Iniciando ingesta de resultados de QuantConnect...")
    
    try:
        # Verificar que existen las credenciales
        if not os.path.exists(QC_SECRETS):
            print(f"❌ Error: No se encontraron credenciales en {QC_SECRETS}")
            return 1
        
        # Leer credenciales
        with open(QC_SECRETS, 'r') as f:
            credentials = json.load(f)
        
        print(f"✅ Credenciales cargadas desde {QC_SECRETS}")
        
        # Ejecutar ingest_qc_results
        result = ingest_qc_results()
        
        if result:
            print("✅ Ingesta completada exitosamente")
            print(f"Resultado: {result}")
            return 0
        else:
            print("⚠️ La ingesta no devolvió resultados")
            return 1
            
    except Exception as e:
        print(f"❌ Error durante la ingesta: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
