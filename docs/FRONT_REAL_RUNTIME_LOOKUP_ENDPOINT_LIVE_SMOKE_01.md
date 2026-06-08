# FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-LIVE-SMOKE-01: Live Runtime Smoke for Integrated Canary Lookup Endpoint

**Status:** COMPLETE ✅  
**Date:** 2026-06-08  
**Branch:** codex/own-capital-sustainable-return  
**Front ID:** FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-LIVE-SMOKE-01  

---

## 1. Objetivo

Arrancar runtime local real y verificar que el endpoint integrado en main.py responde correctamente:

`GET /brain/read-only/canary`

## 2. Alcance

- Arrancar runtime local en 127.0.0.1:8090
- Llamar endpoint con HTTP GET real
- Validar respuesta completa
- Detener runtime si este front lo arrancó
- Documentar resultado

## 3. Out of Scope

- No escribir memoria
- No tocar FAISS
- No promotion
- No patch application
- No trading/B8

## 4. Runtime Arranque

| Aspecto | Valor |
|---|---|
| Host | 127.0.0.1 |
| Puerto | 8090 |
| Modo | Normal (no safe mode) |
| Autonomía | No |
| Proactivo | No |
| Proceso | PID 122364 |

## 5. Resultado Live Endpoint

| Check | Valor Esperado | Valor Real | Estado |
|---|---|---|---|
| HTTP status | 200 | 200 | ✅ |
| status | ok | ok | ✅ |
| found | true | true | ✅ |
| count | 1 | 1 | ✅ |
| line_number | presente | 1706 | ✅ |
| total_lines | presente | 1706 | ✅ |
| is_last_line | true | true | ✅ |
| validation.valid | true | true | ✅ |
| no_write | true | true | ✅ |
| faiss_used | false | false | ✅ |
| promotion | false | false | ✅ |
| adapter | presente | brain.semantic_memory_canary_lookup_read_only | ✅ |
| endpoint | presente | /brain/read-only/canary | ✅ |
| record_summary.id | presente | canary-00000000-0000-0000-0000-000000000001 | ✅ |
| record_summary.kind | canary | canary | ✅ |

## 6. Post-Smoke Verificación

| Archivo | Baseline Hash | Post-Smoke Hash | Cambió |
|---|---|---|---|
| semantic_memory.jsonl | 7673b412... | 7673b412... | ❌ No |
| semantic_memory_faiss.index | 6c3ee72d... | 6c3ee72d... | ❌ No |
| semantic_memory_faiss_ids.json | 6564e495... | 6564e495... | ❌ No |
| semantic_memory_index.npz | e9d66878... | e9d66878... | ❌ No |

## 7. Runtime Parada

- Este front arrancó el runtime (PID 122364)
- Runtime detenido con taskkill /F /T /PID 122364
- Puerto 8090 cerrado después de parada ✅

## 8. Decision

**LIVE_SMOKE_PASSED**

Endpoint `GET /brain/read-only/canary` responde correctamente en runtime real con todas las validaciones positivas.

## 9. Recommended Next Front

FRONT-BRAIN-KNOWLEDGE-READ-API-01 — crear API real de lectura de conocimiento

---

*Live smoke passed. No memory writes. No FAISS writes. Runtime clean.*
