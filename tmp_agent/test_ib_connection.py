import sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import time
import threading

class TestWrapper(EWrapper):
    def __init__(self):
        self.connected = False
        self.next_order_id = None
        self.error_received = False
        
    def nextValidId(self, orderId):
        print(f"[OK] Conectado! Next Valid ID: {orderId}")
        self.next_order_id = orderId
        self.connected = True
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
        print(f"[ERROR] Code {errorCode}: {errorString}")
        self.error_received = True
        if errorCode == 502:
            print("  -> IB Gateway no esta corriendo en el puerto 4002")
        elif errorCode == 504:
            print("  -> No esta conectado a TWS/Gateway")
        elif errorCode == 2104:
            print("  -> Market data OK (no es error)")
            
    def managedAccounts(self, accountsList):
        print(f"[OK] Managed Accounts: {accountsList}")

class TestClient(EClient):
    def __init__(self, wrapper):
        EClient.__init__(self, wrapper)

def main():
    print('=' * 70)
    print('TEST DE CONEXION IB GATEWAY')
    print('=' * 70)
    print()
    print('Intentando conectar a 127.0.0.1:4002 (Client ID: 295)...')
    print()
    
    wrapper = TestWrapper()
    client = TestClient(wrapper)
    
    try:
        client.connect("127.0.0.1", 4002, clientId=295)
        
        # Esperar conexion
        timeout = 10
        start_time = time.time()
        while not wrapper.connected and not wrapper.error_received:
            if time.time() - start_time > timeout:
                print("[TIMEOUT] No se pudo conectar en 10 segundos")
                break
            time.sleep(0.1)
        
        if wrapper.connected:
            print()
            print('[OK] CONEXION EXITOSA!')
            print(f'  Next Order ID: {wrapper.next_order_id}')
            print()
            
            # Pedir cuenta
            print('Solicitando managed accounts...')
            time.sleep(1)
        else:
            print()
            print('[ERROR] No se pudo establecer conexion')
            print()
            print('Posibles causas:')
            print('  1. IB Gateway no esta corriendo')
            print('  2. Puerto incorrecto (no es 4002)')
            print('  3. Client ID en conflicto (usar otro numero)')
            print('  4. API no habilitada en IB Gateway')
        
        client.disconnect()
        print()
        print('[OK] Cliente desconectado')
        
    except Exception as e:
        print(f"[ERROR] Excepcion: {e}")
        import traceback
        traceback.print_exc()
    
    print('=' * 70)

if __name__ == "__main__":
    main()
