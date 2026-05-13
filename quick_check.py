# quick_check.py - Verificación para puerto 8010
import requests
import time

def quick_check():
    print("=== VERIFICACIÓN RÁPIDA (PUERTO 8010) ===")
    
    endpoints = [
        ("Documentación", "/docs"),
        ("Health Check", "/health"),
        ("Financial Metrics", "/financial-autonomy/metrics"),
        ("Financial Status", "/financial-integration/status")
    ]
    
    for name, endpoint in endpoints:
        try:
            start_time = time.time()
            response = requests.get(f"http://localhost:8010{endpoint}", timeout=5)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                print(f"✅ {name}: {response.status_code} ({response_time:.0f}ms)")
            else:
                print(f"⚠️ {name}: {response.status_code} ({response_time:.0f}ms)")
                
        except requests.exceptions.ConnectionError:
            print(f"❌ {name}: NO CONECTADO")
        except requests.exceptions.Timeout:
            print(f"⏰ {name}: TIMEOUT")
        except Exception as e:
            print(f"❌ {name}: ERROR - {e}")

if __name__ == "__main__":
    quick_check()
