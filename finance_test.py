# finance_test.py - Verificación específica del módulo financiero
import requests

def test_financial_module():
    print("=== VERIFICACIÓN MÓDULO FINANCIERO ===")
    
    endpoints = [
        ("Métricas financieras", "/financial-autonomy/metrics"),
        ("Trust score financiero", "/financial-autonomy/trust-score"),
        ("Health del servidor", "/health")
    ]
    
    for name, endpoint in endpoints:
        try:
            response = requests.get(f"http://localhost:8010{endpoint}", timeout=10)
            if response.status_code == 200:
                print(f"✅ {name}: OPERATIVO")
                print(f"   Respuesta: {response.json()}")
            else:
                print(f"⚠️ {name}: {response.status_code}")
        except Exception as e:
            print(f"❌ {name}: {e}")

if __name__ == "__main__":
    test_financial_module()
