# start_corrected.py - Inicio en puerto 8010 corregido
import subprocess
import sys
import time
import requests

def start_corrected_server():
    print("🚀 INICIANDO SERVIDOR CORREGIDO (PUERTO 8010)...")
    
    # Iniciar servidor
    process = subprocess.Popen([
        sys.executable, r"C:\AI_VAULT\brain_server_emergency.py"
    ])
    
    print("Esperando inicio del servidor...")
    time.sleep(10)  # Más tiempo para inicio completo
    
    # Verificar
    try:
        response = requests.get("http://localhost:8010/", timeout=15)
        if response.status_code == 200:
            print("✅ Servidor iniciado correctamente en puerto 8010!")
            print("📊 Estado:", response.json())
            
            # Verificar endpoints financieros
            try:
                finance_response = requests.get("http://localhost:8010/financial-autonomy/metrics", timeout=10)
                if finance_response.status_code == 200:
                    print("✅ Módulo financiero operativo")
                    print("📈 Respuesta:", finance_response.json())
                else:
                    print(f"⚠️ Módulo financiero: {finance_response.status_code}")
            except Exception as e:
                print(f"❌ Módulo financiero error: {e}")
            
            return True
        else:
            print(f"⚠️ Servidor responde con código: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error conectando al servidor: {e}")
        
        # Verificar si el proceso está vivo
        if process.poll() is None:
            print("⚠️ Proceso todavía corriendo, pero no responde")
        else:
            print("❌ Proceso se cerró")
            
        return False

if __name__ == "__main__":
    success = start_corrected_server()
    if success:
        print("🎯 ¡Sistema financiero-autónomo operativo en puerto 8010!")
        print("🌐 Abre: http://localhost:8010/docs")
        print("💰 Financial: http://localhost:8010/financial-autonomy/metrics")
        print("🔧 Health: http://localhost:8010/health")
        
        # Mantener el script corriendo
        print("Presiona Ctrl+C para detener el servidor...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Deteniendo servidor...")
    else:
        print("❌ Falló el inicio del servidor")
