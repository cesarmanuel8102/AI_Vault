#!/usr/bin/env python3
"""
Tests Fase 0: Preparación Crítica
Verifica que el sistema está listo para construir el agente
"""

import json
import urllib.request
import sys

BASE_URL = "http://127.0.0.1:8090"
OLLAMA_URL = "http://127.0.0.1:11434"

class TestFase0:
    """Tests de verificación de Fase 0"""
    
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def test_ollama_connectivity(self):
        """Test 1: Ollama responde en < 5 segundos"""
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                models = [m['name'] for m in data.get('models', [])]
                
                # Verificar que qwen2.5:14b está disponible
                if 'qwen2.5:14b' in models:
                    self.log_pass("Test 1", f"Ollama responde en <5s. Modelos disponibles: {len(models)}")
                    return True
                else:
                    self.log_fail("Test 1", f"qwen2.5:14b NO disponible. Modelos: {models}")
                    return False
        except Exception as e:
            self.log_fail("Test 1", f"Ollama no responde: {e}")
            return False
    
    def test_brain_chat_health(self):
        """Test 2: Brain Chat responde health check"""
        try:
            req = urllib.request.Request(f"{BASE_URL}/health", method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                if data.get('status') == 'healthy':
                    self.log_pass("Test 2", f"Brain Chat healthy. Versión: {data.get('version')}")
                    return True
                else:
                    self.log_fail("Test 2", f"Brain Chat no healthy: {data}")
                    return False
        except Exception as e:
            self.log_fail("Test 2", f"Brain Chat no responde: {e}")
            return False
    
    def test_chat_endpoint(self):
        """Test 3: Endpoint /chat responde POST"""
        try:
            payload = json.dumps({"message": "hola", "user_id": "test"}).encode()
            req = urllib.request.Request(
                f"{BASE_URL}/chat",
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                if data.get('success'):
                    self.log_pass("Test 3", "Endpoint /chat funciona correctamente")
                    return True
                else:
                    self.log_fail("Test 3", f"/chat retorna error: {data.get('error')}")
                    return False
        except Exception as e:
            self.log_fail("Test 3", f"/chat no responde: {e}")
            return False
    
    def test_tools_available(self):
        """Test 4: Herramientas están disponibles"""
        try:
            # Verificar que podemos ejecutar un comando simple
            payload = json.dumps({"message": "ejecuta comando echo test", "user_id": "test"}).encode()
            req = urllib.request.Request(
                f"{BASE_URL}/chat",
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())
                if data.get('success') and 'test' in data.get('message', '').lower():
                    self.log_pass("Test 4", "Herramientas disponibles y funcionando")
                    return True
                else:
                    self.log_fail("Test 4", f"Herramientas no responden correctamente: {data}")
                    return False
        except Exception as e:
            self.log_fail("Test 4", f"Error ejecutando herramientas: {e}")
            return False
    
    def log_pass(self, test_name, message):
        self.results.append(f"[PASS] {test_name}: {message}")
        self.passed += 1
    
    def log_fail(self, test_name, message):
        self.results.append(f"[FAIL] {test_name}: {message}")
        self.failed += 1
    
    def run_all(self):
        """Ejecutar todos los tests"""
        print("=" * 70)
        print("FASE 0: TESTS DE PREPARACIÓN")
        print("=" * 70)
        print()
        
        self.test_ollama_connectivity()
        self.test_brain_chat_health()
        self.test_chat_endpoint()
        self.test_tools_available()
        
        print()
        print("=" * 70)
        print("RESULTADOS")
        print("=" * 70)
        for result in self.results:
            print(result)
        print()
        print(f"Total: {self.passed + self.failed} tests")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {self.passed/(self.passed + self.failed)*100:.1f}%")
        print()
        
        if self.failed == 0:
            print("FASE 0 COMPLETADA - Sistema listo para Fase 1")
            return 0
        else:
            print("FASE 0 FALLIDA - Corregir errores antes de continuar")
            return 1

if __name__ == "__main__":
    tester = TestFase0()
    sys.exit(tester.run_all())
