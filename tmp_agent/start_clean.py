import subprocess
import time
import os

# Detener procesos previos
print("Deteniendo procesos existentes...")
os.system('taskkill /F /IM python.exe')
os.system('taskkill /F /IM pythonw.exe')
time.sleep(3)

# Iniciar Brain V9 (sin ventana visible)
print("Iniciando Brain V9...")
subprocess.Popen(
    ['pythonw.exe', '-m', 'brain_v9.main'],
    cwd=r'C:\AI_VAULT\tmp_agent',
    stdout=open(r'C:\AI_VAULT\tmp_agent\logs\brain_v9.log', 'w'),
    stderr=subprocess.STDOUT
)

time.sleep(5)

# Iniciar Dashboard (sin ventana visible)
print("Iniciando Dashboard...")
subprocess.Popen(
    ['pythonw.exe', 'dashboard_server.py'],
    cwd=r'C:\AI_VAULT\00_identity\autonomy_system',
    stdout=open(r'C:\AI_VAULT\00_identity\autonomy_system\dashboard.log', 'w'),
    stderr=subprocess.STDOUT
)

print("Servicios iniciados. Espera 10 segundos...")
time.sleep(10)

# Verificar
import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=5) as resp:
        print("Brain V9: OK")
except:
    print("Brain V9: No responde aun")

try:
    with urllib.request.urlopen('http://127.0.0.1:8070/api/health', timeout=5) as resp:
        print("Dashboard: OK")
except:
    print("Dashboard: No responde aun")

print("\nPresiona Enter para cerrar...")
input()
