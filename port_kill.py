# port_kill.py - Liberar puerto 8000 y reiniciar
import socket
import os
import subprocess
import time

def kill_process_on_port(port=8000):
    \"\"\"Matar proceso usando el puerto 8000\"\"\"
    try:
        # En Windows usar netstat
        result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        
        for line in lines:
            if f\":{port} \" in line and \"LISTENING\" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit():
                    print(f\"🔪 Matando proceso PID {pid} usando puerto {port}\"")
                    subprocess.run(['taskkill', '/f', '/pid', pid], capture_output=True)
                    return True
        return False
    except Exception as e:
        print(f\"Error: {e}\"")
        return False

def start_brain_server():
    \"\"\"Reiniciar Brain Server\"\"\"
    print(\"🚀 Reiniciando Brain Server...\"")
    
    # Buscar el brain_server más reciente
    import glob
    brain_files = glob.glob(\"C:/AI_VAULT/**/brain_server*.py\", recursive=True)
    if not brain_files:
        print(\"❌ No se encontró brain_server.py\"")
        return False
    
    latest_brain = max(brain_files, key=os.path.getmtime)
    print(f\"📄 Ejecutando: {latest_brain}\"")
    
    # Ejecutar en segundo plano
    try:
        process = subprocess.Popen([
            'python', latest_brain
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Esperar un poco para que inicie
        time.sleep(5)
        
        # Verificar si está corriendo
        try:
            import requests
            response = requests.get(\"http://localhost:8000/docs\", timeout=10)
            if response.status_code == 200:
                print(\"✅ Brain Server reiniciado exitosamente\"")
                return True
            else:
                print(f\"⚠️ Server responde con código: {response.status_code}\"")
                return False
        except:
            print(\"❌ Server no responde después del reinicio\"")
            return False
            
    except Exception as e:
        print(f\"❌ Error al ejecutar: {e}\"")
        return False

if __name__ == \"__main__\":
    # Liberar puerto primero
    if kill_process_on_port(8000):
        print(\"✅ Puerto 8000 liberado\"")
    else:
        print(\"✅ No había proceso usando puerto 8000\"")
    
    # Reiniciar servidor
    start_brain_server()
