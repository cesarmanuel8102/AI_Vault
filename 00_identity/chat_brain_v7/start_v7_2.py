"""
Brain Chat V7.2 - Iniciador con RSI Estratégico
Versión integrada que combina V7 + RSI Estratégico Alineado
"""

import sys
import os
sys.path.insert(0, r'C:\AI_VAULT\00_identity\chat_brain_v7')

# Establecer variables de entorno
os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', '')

print("🚀 Iniciando Brain Chat V7.2 con RSI Estratégico...")
print("📁 Cargando módulos...")

# Ejecutar el archivo principal que incluye RSI
exec(open(r'C:\AI_VAULT\00_identity\chat_brain_v7\brain_chat_v7_2_integrated.py').read())
