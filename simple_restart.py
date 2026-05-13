# simple_restart.py - Reinicio simple sin errores de sintaxis
import os
import time
import subprocess
import sys

def simple_restart():
    print("=== REINICIO SIMPLE DEL BRAIN SERVER ===")
    
    # Paso 1: Cerrar procesos Python existentes
    print("1. Cerrando procesos Python...")
    os.system("taskkill /f /im python.exe >nul 2>&1")
    os.system("taskkill /f /im python3.exe >nul 2>&1")
    time.sleep(2)
    
    # Paso 2: Liberar puerto 8000 específicamente
    print("2. Liberando puerto 8000...")
    os.system("netstat -ano | findstr :8000 > port_check.txt")
    
    try:
        with open("port_check.txt", "r") as f:
            for line in f:
                if "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit():
                            print(f"   Cerrando proceso PID {pid} en puerto 8000")
                            os.system(f"taskkill /f /pid {pid} >nul 2>&1")
    except:
        pass
    
    time.sleep(1)
    
    # Paso 3: Encontrar brain_server más reciente
    print("3. Buscando brain_server más reciente...")
    brain_server_path = None
    latest_mtime = 0
    
    for root, dirs, files in os.walk("C:\\AI_VAULT"):
        for file in files:
            if file.startswith("brain_server") and file.endswith(".py"):
                full_path = os.path.join(root, file)
                file_mtime = os.path.getmtime(full_path)
                if file_mtime > latest_mtime:
                    latest_mtime = file_mtime
                    brain_server_path = full_path
    
    if not brain_server_path:
        print("ERROR: No se encontró brain_server.py")
        return False
    
    print(f"   Encontrado: {brain_server_path}")
    
    # Paso 4: Reiniciar Brain Server
    print("4. Reiniciando Brain Server...")
    
    try:
        # Ejecutar en proceso separado
        process = subprocess.Popen([
            sys.executable, brain_server_path
        ])
        
        print("   Proceso iniciado, esperando inicio...")
        time.sleep(8)
        
        # Verificar si está vivo
        try:
            import requests
            response = requests.get("http://localhost:8000/docs", timeout=10)
            if response.status_code == 200:
                print("✅ Brain Server reiniciado exitosamente")
                print("📊 Documentación: http://localhost:8000/docs")
                print("💰 Finanzas: http://localhost:8000/financial-autonomy/metrics")
                return True
            else:
                print(f"⚠️ Server responde con código: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error verificando servidor: {e}")
            print("   Pero el proceso puede estar corriendo...")
            return True
            
    except Exception as e:
        print(f"❌ Error al ejecutar: {e}")
        return False

if __name__ == "__main__":
    simple_restart()
