# verification.py
import requests
import time

def verify_integration():
    print(\"🔍 Verificando integración financiera...\")
    
    # Esperar un momento para que el servidor procese los cambios
    time.sleep(2)
    
    try:
        # Probar endpoint de verificación
        response = requests.get(\"http://localhost:8000/financial-integration/status\", timeout=5)
        if response.status_code == 200:
            print(\"✅ Endpoint de integración RESPONDE\"")
            print(f\"   Estado: {response.json()}\"")
            return True
        else:
            print(f\"❌ Endpoint responde con código: {response.status_code}\"")
            return False
    except Exception as e:
        print(f\"❌ No se pudo conectar al endpoint: {e}\"")
        print(\"   El Brain Server puede necesitar reinicio\"")
        return False

def check_financial_endpoints():
    print(\"🔍 Verificando endpoints financieros...\")
    
    endpoints = [
        \"/financial-autonomy/metrics\",
        \"/financial-autonomy/optimize\", 
        \"/financial-autonomy/trust-score\"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f\"http://localhost:8000{endpoint}\", timeout=5)
            if response.status_code == 200:
                print(f\"✅ {endpoint} - OPERATIVO\"")
            else:
                print(f\"⚠️ {endpoint} - Código: {response.status_code}\"")
        except Exception as e:
            print(f\"❌ {endpoint} - Error: {e}\"")

if __name__ == \"__main__\":
    verify_integration()
    check_financial_endpoints()
