#!/usr/bin/env python3
"""
Test simple de conexion IB Gateway
"""
import sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
import time

class SimpleWrapper(EWrapper):
    def __init__(self):
        self.connected = False
        
    def nextValidId(self, orderId):
        print(f"[OK] Conectado! Order ID: {orderId}")
        self.connected = True
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
        # Solo mostrar errores reales, no warnings
        if errorCode not in [2104, 2106, 2107, 2108, 2157, 2158]:
            print(f"[ERROR] {errorCode}: {errorString}")
            if errorCode == 502:
                print("  -> IB Gateway no responde")
            elif errorCode == 504:
                print("  -> Verificar que IB Gateway este corriendo")

def main():
    print("=" * 70)
    print("TEST SIMPLE IB GATEWAY")
    print("=" * 70)
    print()
    
    wrapper = SimpleWrapper()
    client = EClient(wrapper)
    
    print("Conectando a 127.0.0.1:4002 (Client ID: 999)...")
    
    try:
        client.connect("127.0.0.1", 4002, clientId=999)
        
        # Esperar 15 segundos maximo
        for i in range(150):
            if wrapper.connected:
                print()
                print("=" * 70)
                print("[OK] CONEXION EXITOSA!")
                print("=" * 70)
                time.sleep(1)
                break
            time.sleep(0.1)
        else:
            print()
            print("=" * 70)
            print("[TIMEOUT] No se recibio respuesta de IB Gateway")
            print("=" * 70)
        
        client.disconnect()
        
    except Exception as e:
        print(f"[EXCEPTION] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
