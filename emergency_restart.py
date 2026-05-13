# emergency_restart.py - Reinicio completo del sistema
import os
import time
import subprocess
import requests

def emergency_restart():
    print(\"🆕 REINICIO DE EMERGENCIA DEL SISTEMA\"")
    print(\"=\" * 50)
    
    # Paso 1: Matar todos los procesos Python
    print(\"1. Cerrando todos los procesos Python...\"")
    os.system(\"taskkill /f /im python.exe >nul 2>&1\")
    os.system(\"taskkill /f /im python3.exe >nul 2>&1\")
    time.sleep(3)
    
    # Paso 2: Liberar puerto 8000
    print(\"2. Liberando puerto 8000...\"")
    os.system(\"netstat -ano | findstr :8000 > port_check.txt\"")
    with open(\"port_check.txt\", \"r\") as f:
        for line in f:
            if \"LISTENING\" in line:
                pid = line.strip().split()[-1]
                if pid.isdigit():
                    os.system(f\"taskkill /f /pid {pid} >nul 2>&1\"")
    time.sleep(2)
    
    # Paso 3: Encontrar brain_server más reciente
    print(\"3. Buscando brain_server más reciente...\"")
    brain_server_path = None
    for root, dirs, files in os.walk(\"C:\\\\AI_VAULT\"):
        for file in files:
            if file.startswith(\"brain_server\") and file.endswith(\".py\"):
                full_path = os.path.join(root, file)
                if brain_server_path is None or os.path.getmtime(full_path) > os.path.getmtime(brain_server_path):
                    brain_server_path = full_path
    
    if not brain_server_path:
        print(\"❌ No se encontró brain_server.py\"")
        return False
    
    print(f\"   Encontrado: {brain_server_path}\"")
    
    # Paso 4: Reiniciar en nuevo proceso
    print(\"4. Reiniciando Brain Server...\"")
    
    # Crear script de arranque separado
    startup_script = f\"\"\"
import subprocess
import time
import sys

print(\"Starting Brain Server...\")
process = subprocess.Popen([
    sys.executable, \"{brain_server_path}\"
], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

# Esperar y verificar
time.sleep(10)

# Verificar si está vivo
try:
    import requests
    response = requests.get(\"http://localhost:8000/docs\", timeout=15)
    if response.status_code == 200:
        print(\"✅ Brain Server iniciado correctamente\"")
        print(\"📊 Docs disponibles en: http://localhost:8000/docs\"")
        print(\"🔧 Financial endpoints: http://localhost:8000/financial-autonomy/metrics\"")
    else:
        print(f\"⚠️ Status code: {{response.status_code}}\"")
except Exception as e:
    print(f\"❌ Error: {{e}}\"")
\"\"\"
    
    with open(\"C:\\\\AI_VAULT\\\\start_brain.py\", \"w\") as f:
        f.write(startup_script)
    
    # Ejecutar en proceso separado
    subprocess.Popen([
        \"python\", \"C:\\\\AI_VAULT\\\\start_brain.py\" 
    ], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    print(\"✅ Proceso de reinicio lanzado en nueva ventana\"")
    return True

if __name__ == \"__main__\":
    emergency_restart()
