#!/usr/bin/env python
"""
Verificar estado del dashboard
"""
import requests
import json

def check_dashboard():
    try:
        # Verificar página principal
        response = requests.get("http://127.0.0.1:8072/", timeout=5)
        if response.status_code == 200:
            print("✅ Dashboard server: RUNNING (port 8072)")
        else:
            print(f"⚠️  Dashboard server: HTTP {response.status_code}")
            return False

        # Verificar endpoint de utility governance
        try:
            utility_response = requests.get("http://127.0.0.1:8072/brain/utility-governance/status", timeout=5)
            if utility_response.status_code == 200:
                utility_data = utility_response.json()
                u_score = utility_data.get('u_proxy_score', 'N/A')
                print(f"✅ Utility U API: {u_score}")
                if u_score == -0.0756:
                    print("   🎯 Utility U: CORRECTO (-0.0756)")
                else:
                    print(f"   ⚠️  Utility U: INCORRECTO (esperado -0.0756, actual {u_score})")
            else:
                print(f"⚠️  Utility U API: HTTP {utility_response.status_code}")
        except Exception as e:
            print(f"⚠️  Utility U API: ERROR - {e}")

        # Verificar endpoint de plataformas
        try:
            platforms_response = requests.get("http://127.0.0.1:8072/brain/platforms/status", timeout=5)
            if platforms_response.status_code == 200:
                platforms_data = platforms_response.json()
                ibkr_status = platforms_data.get('ibkr', {}).get('status', 'unknown')
                print(f"✅ Platforms API: IBKR status = {ibkr_status}")
                if ibkr_status == 'available':
                    print("   🎯 IBKR Dashboard: CORRECTO (available)")
                else:
                    print(f"   ⚠️  IBKR Dashboard: INCORRECTO (esperado 'available', actual '{ibkr_status}')")
            else:
                print(f"⚠️  Platforms API: HTTP {platforms_response.status_code}")
        except Exception as e:
            print(f"⚠️  Platforms API: ERROR - {e}")

        return True

    except requests.exceptions.ConnectionError:
        print("❌ Dashboard server: NOT RUNNING (connection refused)")
        return False
    except Exception as e:
        print(f"❌ Dashboard check: ERROR - {e}")
        return False

if __name__ == "__main__":
    print("\n🔍 VERIFICANDO DASHBOARD...")
    check_dashboard()
    print("\n📋 ACCIONES RECOMENDADAS:")
    print("   • Si no está corriendo: Reiniciar servidor")
    print("   • Si IBKR no es 'available': Verificar dashboard_platforms.py")
    print("   • Si Utility U no es -0.0756: Verificar utility_u_latest.json")