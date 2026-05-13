#!/usr/bin/env python
"""
Parallel Task A: Validate IBKR Lane Signal Health
"""
import sys
import json
import socket

sys.path.append('tmp_agent')

def main():
    print("\n" + "=" * 80)
    print("[TASK A] VALIDANDO IBKR LANE - SIGNAL HEALTH CHECK")
    print("=" * 80)
    
    # Port connectivity test
    print("\n[1] Comprobando conectividad puerto 4002...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 4002))
    sock.close()
    
    if result == 0:
        print("✓ Puerto 4002 (IB Gateway): ESCUCHANDO")
    else:
        print("✗ Puerto 4002 (IB Gateway): NO ACCESIBLE")
        return 1
    
    # IBKR connector health
    print("\n[2] Verificando health del conector IBKR...")
    try:
        from brain_v9.trading.connectors import IBKRReadonlyConnector
        ibkr_conn = IBKRReadonlyConnector()
        # health es async, skip por ahora
        print("✓ Conector IBKR importable")
    except Exception as e:
        print(f"✗ Error importando IBKR Connector: {e}")
        return 1
    
    # Paper order API check
    print("\n[3] Comprobando API de órdenes paper (ib_insync)...")
    try:
        from brain_v9.trading.ibkr_order_executor import check_ibkr_paper_order_api
        result = check_ibkr_paper_order_api(symbol="SPY", action="BUY", quantity=1, what_if=True)
        
        connected = result.get("connected", False)
        api_ready = result.get("order_api_ready", False)
        accounts = result.get("managed_accounts", [])
        
        print(f"✓ Conectado: {connected}")
        print(f"✓ API Ready: {api_ready}")
        print(f"✓ Cuentas: {accounts}")
        
        if connected and api_ready:
            print("\n✓ IBKR LANE HEALTH: LISTO PARA FLUJO DE SIGNALS")
            return 0
        else:
            print("\n⚠ IBKR LANE HEALTH: PARCIAL")
            return 1
            
    except Exception as e:
        print(f"✗ Error en check_ibkr_paper_order_api: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
