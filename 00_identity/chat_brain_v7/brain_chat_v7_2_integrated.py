"""
Brain Chat V7.2 - Version Integrada con RSI Estrategico
Combina autoconciencia profunda + RSI priorizado por premisas canonicas v3.1
"""

import sys
import os

# Configurar paths
os.chdir(r'C:\AI_VAULT\00_identity\chat_brain_v7')
sys.path.insert(0, r'C:\AI_VAULT\00_identity\chat_brain_v7')

print("Brain Chat V7.2 - Integrando RSI Estrategico...")
print("=" * 60)

# Ejecutar version base
exec(open('brain_chat_v7.py', 'r', encoding='utf-8').read())

print("Autoconciencia Profunda: Cargada")

# Agregar RSI Estrategico
print("RSI Estrategico Alineado: Cargando...")

# Importar funciones RSI
exec(open('brain_chat_v7_2_strategic_rsi_aligned.py', 'r', encoding='utf-8').read())

print("RSI Estrategico Alineado: Listo")
print("=" * 60)
print("Brain Chat V7.2 Operativo")
print("   - Autoconciencia: Activa")
print("   - RSI Estrategico: Activo")
print("   - Ciclo automatico: Cada 60 minutos")
print("   - Fase actual: Fase 1 (Autoconciencia y Robustez)")
print("Comandos RSI disponibles:")
print("   - 'rsi estrategico' -> Analisis completo")
print("   - 'brechas' -> Brechas estrategicas")
print("   - 'fase' -> Estado de fase actual")
print("   - 'progreso' -> Progreso hacia objetivos")
print("=" * 60)

# Iniciar servidor automaticamente
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="info")
