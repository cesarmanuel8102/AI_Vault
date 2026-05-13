# test_start.py - Probar inicio para ver errores
import subprocess
import sys
import time

print("=== PROBANDO INICIO DE BRAIN SERVER ===")

try:
    # Ejecutar brain_server directamente para capturar errores
    process = subprocess.Popen([
        sys.executable, r"C:\AI_VAULT\00_identity\brain_server.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Esperar un poco y capturar salida
    time.sleep(3)
    
    # Intentar leer salida
    try:
        stdout, stderr = process.communicate(timeout=2)
        print("STDOUT:", stdout)
        print("STDERR:", stderr)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        print("STDOUT (timeout):", stdout)
        print("STDERR (timeout):", stderr)
    
    print("Código de salida:", process.returncode)
    
except Exception as e:
    print("Error ejecutando:", e)
