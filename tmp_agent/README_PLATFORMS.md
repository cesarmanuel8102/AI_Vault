# Sistema de Plataformas Separadas - AI_VAULT

## 🚀 ESTADO ACTUAL

Se ha implementado el sistema de plataformas separadas con U scores independientes.

## ✅ ARCHIVOS CREADOS

### Core System
- `brain_v9/trading/platform_manager.py` - Gestión de plataformas y U scores
- `brain_v9/autonomy/platform_accumulators.py` - Acumuladores independientes
- `brain_v9/trading/platform_dashboard_api.py` - API de monitoreo
- `brain_v9/init_platforms.py` - Inicializador

### Scripts
- `restart_complete.bat` - Reinicio completo del sistema
- `services.bat` - Control de servicios
- `monitor.py` - Monitor de auto-recuperación

## 🌐 NUEVOS ENDPOINTS

```
GET /api/platforms/summary              - Resumen de todas las plataformas
GET /api/platforms/{name}               - Detalle de una plataforma
GET /api/platforms/{name}/u-history     - Historial de U
GET /api/platforms/{name}/signals-analysis - Análisis de señales
GET /api/platforms/compare              - Comparación entre plataformas
```

## 📊 PLATAFORMAS CONFIGURADAS

### PocketOption
- **Revisión**: Cada 1 minuto
- **Min sample**: 0.20
- **Min entries**: 5
- **Símbolos**: EURUSD_otc, USDCHF_otc, GBPUSD_otc, AUDNZD_otc

### IBKR
- **Revisión**: Cada 5 minutos
- **Min sample**: 0.30
- **Min entries**: 8
- **Símbolos**: SPY, AAPL, QQQ, TSLA

### Internal Paper
- **Revisión**: Cada 2 minutos
- **Min sample**: 0.25
- **Min entries**: 5
- **Símbolos**: EURUSD_otc, SPY

## 🔧 INTEGRACIÓN CON DASHBOARD

Los endpoints están integrados en `dashboard_server.py`.

Para acceder:
1. Abrir: http://127.0.0.1:8070
2. Navegar a: /api/platforms/summary

## 📝 PRÓXIMOS PASOS

Para completar la integración visual, necesitas:

1. **Agregar sección al HTML del dashboard**:
   - Crear tabla de plataformas
   - Mostrar U scores
   - Gráficos comparativos

2. **Actualizar JavaScript**:
   - Consumir endpoints de plataformas
   - Actualizar cada 30 segundos
   - Alertas de estado

## ⚠️ NOTA IMPORTANTE

Los servicios están iniciándose. Espera 30-60 segundos para que:
- Brain V9 esté listo en puerto 8090
- Dashboard responda en puerto 8070
- Plataformas comiencen acumulación

---
**Implementado:** 2026-03-25
**Versión:** Brain V9 + Plataformas Separadas v1.0
