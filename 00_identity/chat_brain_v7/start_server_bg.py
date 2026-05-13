import subprocess
import sys

# Iniciar servidor Brain Chat V8.1 en segundo plano
print("Iniciando Brain Chat V8.1...")

process = subprocess.Popen(
    [sys.executable, "brain_chat_v81_integrated.py"],
    stdout=open("server_v81.log", "w"),
    stderr=subprocess.STDOUT,
    cwd=r"C:\AI_VAULT\00_identity\chat_brain_v7"
)

print(f"Servidor iniciado con PID: {process.pid}")
print("Esperando 5 segundos para inicialización...")

import time
time.sleep(5)

# Verificar que está corriendo
try:
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8090/health", timeout=5)
    print(f"Servidor responde: {r.read().decode()}")
    print(f"Servidor V8.1 está CORRIENDO en http://127.0.0.1:8090")
    print(f"Interfaz Web: http://127.0.0.1:8090/ui")
except Exception as e:
    print(f"Verificando... Reintento en 3 segundos")
    time.sleep(3)
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:8090/health", timeout=5)
        print(f"Servidor V8.1 está CORRIENDO!")
    except Exception as e2:
        print(f"No se pudo verificar el servidor: {e2}")

print(f"PID del servidor: {process.pid}")
print("Para detener: taskkill /PID {process.pid} /F")
