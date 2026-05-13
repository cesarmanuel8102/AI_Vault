# dashboard_check.py - Verificar dashboard
import requests

def check_dashboard():
    print("=== VERIFICANDO DASHBOARD ===")
    
    # El dashboard original usa puerto 8010
    try:
        response = requests.get("http://localhost:8010/", timeout=10)
        if response.status_code == 200:
            print("✅ Dashboard responde en puerto 8010")
            print(f"   Estado: {response.json()}")
            return True
        else:
            print(f"⚠️ Dashboard: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Dashboard no disponible: {e}")
        return False

if __name__ == "__main__":
    check_dashboard()
