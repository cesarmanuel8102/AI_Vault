# start_emergency_corrected.py - Inicio garantizado
import subprocess
import sys
import time
import requests

def start_emergency_server():
    print("🚀 INICIANDO SERVIDOR DE EMERGENCIA CORREGIDO...")
    
    # Iniciar servidor
    process = subprocess.Popen([
        sys.executable, r"C:\AI_VAULT\brain_server_emergency.py"
    ])
    
    print("Esperando inicio del servidor...")
    time.sleep(8)
    
    # Verificar
    try:
        response = requests.get("http://localhost:8010/", timeout=10)
        if response.status_code == 200:
            print("✅ Servidor de emergencia iniciado correctamente!")
            print("📊 Estado:", response.json())
            
            # Verificar endpoints financieros
            try:
                finance_response = requests.get("http://localhost:8010/financial-autonomy/metrics", timeout=5)
                if finance_response.status_code == 200:
                    print("✅ Módulo financiero operativo")
                else:
                    print(f"⚠️ Módulo financiero: {finance_response.status_code}")
            except:
                print("❌ Módulo financiero no responde")
            
            return True
        else:
            print(f"⚠️ Servidor responde con código: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error conectando al servidor: {e}")
        return False

if __name__ == "__main__":
    success = start_emergency_server()
    if success:
        print("🎯 ¡Sistema financiero-autónomo operativo!")
        print("🌐 Abre: http://localhost:8010/docs")
        print("💰 Financial: http://localhost:8010/financial-autonomy/metrics")
    else:
        print("❌ Falló el inicio del servidor de emergencia")

