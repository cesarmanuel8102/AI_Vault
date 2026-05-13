# start_brain_reliable.py - Inicio confiable del Brain Server
import subprocess
import time
import sys
import os

def start_brain():
    print("=== INICIANDO BRAIN SERVER ===")
    
    # Ruta al brain_server más reciente
    brain_path = r"C:\AI_VAULT\00_identity\brain_server.py"
    
    print(f"Iniciando: {brain_path}")
    
    # Ejecutar en proceso separado
    process = subprocess.Popen([
        sys.executable, brain_path
    ])
    
    print("Esperando inicio del servidor...")
    
    # Esperar más tiempo para inicio completo
    for i in range(30):  # 30 segundos máximo
        time.sleep(1)
        print(f"Esperando... {i+1}/30 segundos")
        
        # Verificar si el proceso todavía está vivo
        if process.poll() is not None:
            print("❌ El proceso de Brain Server se cerró inesperadamente")
            return False
            
        # Intentar conectar después de 5 segundos
        if i >= 5:
            try:
                import requests
                response = requests.get("http://localhost:8000/docs", timeout=5)
                if response.status_code == 200:
                    print("✅ Brain Server iniciado correctamente!")
                    print("📊 Documentación: http://localhost:8000/docs")
                    print("💰 Módulo financiero: http://localhost:8000/financial-autonomy/metrics")
                    print("🔧 Health: http://localhost:8000/health")
                    return True
            except:
                continue
    
    print("⚠️ El servidor no respondió después de 30 segundos")
    print("   Pero puede estar iniciando lentamente...")
    return True

if __name__ == "__main__":
    start_brain()
