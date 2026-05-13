#!/bin/bash
# TEST_BRAIN_V3_AUTH.sh
# Script para probar el endpoint Brain V3 con autenticación

echo "=========================================="
echo "TEST: Brain V3.0 Endpoint con Auth"
echo "=========================================="

# Paso 1: Solicitud sin credenciales (debe pedir auth)
echo ""
echo "[TEST 1] Solicitud sin credenciales..."
curl -s -X POST http://127.0.0.1:8090/chat/v3 \
  -H "Content-Type: application/json" \
  -d '{"message": "Elimina PocketOption", "session_id": "test1"}' | python -m json.tool 2>/dev/null || echo "Error en respuesta"

echo ""
echo ""

# Paso 2: Solicitud con credenciales (debe ejecutar)
echo "[TEST 2] Solicitud CON credenciales..."
curl -s -X POST http://127.0.0.1:8090/chat/v3 \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Elimina PocketOption",
    "session_id": "test2",
    "credenciales": {
      "username": "dev_admin",
      "password": "dev_admin_2026!",
      "mfa_code": "123456",
      "witnesses": ["testigo1", "testigo2"]
    }
  }' | python -m json.tool 2>/dev/null || echo "Error en respuesta"

echo ""
echo ""

# Paso 3: Cerrar sesión
echo "[TEST 3] Cerrar sesión..."
curl -s -X POST http://127.0.0.1:8090/chat/v3 \
  -H "Content-Type: application/json" \
  -d '{
    "message": "CERRAR SESION DESARROLLADOR",
    "session_id": "test2"
  }' | python -m json.tool 2>/dev/null || echo "Error en respuesta"

echo ""
echo "=========================================="
echo "Test completado"
echo "=========================================="