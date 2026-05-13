# soft_stop.py - Detención suave via API
import requests
import time
import os
import signal

def soft_stop_brain():
    print(\"🔄 Intentando detención suave del Brain Server...\")
    
    try:
        # Enviar señal de shutdown via API
        response = requests.post(\"http://localhost:8000/shutdown\", timeout=5)
        print(\"✅ Señal de shutdown enviada\"")
        return True
    except Exception as e:
        print(f\"❌ No se pudo enviar shutdown: {e}\"")
        return False

def kill_python_processes():
    print(\"🔪 Forzando cierre de procesos Python...\")
    
    # Encontrar procesos Python relacionados con AI_VAULT
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'brain_server' in cmdline or 'AI_VAULT' in cmdline:
                        print(f\"Cerrando PID {proc.info['pid']}: {cmdline}\"")
                        proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        print(\"⚠️ psutil no disponible, usando método alternativo\"")
        # Método alternativo con taskkill
        os.system(\"taskkill /f /im python.exe 2>nul\")
        os.system(\"taskkill /f /im python3.exe 2>nul\")

if __name__ == \"__main__\":
    if not soft_stop_brain():
        print(\"🔧 Falló detención suave, usando método forzado...\")
        kill_python_processes()
    
    # Esperar que los procesos se cierren
    time.sleep(3)
    print(\"✅ Procedimiento de detención completado\")
