# cycle_03

- goal: strengthen CEI/FDOT usefulness
- provider: codex / gpt-5.5
- risk: BLOCKED
- decision: block
- no_cot_leak: True
- memory_faiss_unchanged: True

## Brain proposal

- Mejora: añadir “CEI/FDOT impact diff” por patch candidato: antes/después de cada cambio LOW/MEDIUM, calcular si mejora cobertura de evidencia, reduce ambigüedad de edge o aumenta trazabilidad contexto→decisión, sin escribir FAISS.
- Riesgo: sobreoptimizar métricas internas y aprobar patches que parecen útiles pero no mejoran decisiones reales de trading.
- Test: ejecutar en modo shadow sobre 10-20 casos recientes de learning/posttrade/context-edge y comparar si el diff identifica correctamente cambios útiles, neutros y dañinos.
- Evidencia: CEI/FDOT ya depende de utilidad contextual; medir delta explícito por patch convierte la autorización LOW/MEDIUM en una decisión gobernada por evidencia, no solo por revisión estructural.

## Revised

Acción segura propuesta: crear el artefacto mínimo `docs/cei_fdot_usefulness.md` con una matriz breve CEI/FDOT que defina para cada señal: propósito, entrada canónica requerida, criterio de utilidad, caso donde no debe usarse y métrica existente que la valida; no tocar rutas protegidas ni modificar servicios, código productivo, memoria, FAISS o configuración.
Test exacto: ejecutar `python -m pytest tests/test_cei_fdot_usefulness_docs.py` y exigir que valide existencia del archivo, presencia de las secciones CEI y FDOT, ausencia de rutas protegidas documentadas como destino de escritura, y presencia explícita de criterios de utilidad basados solo en datos canónicos existentes.
Rollback obligatorio: eliminar únicamente `docs/cei_fdot_usefulness.md` y `tests/test_cei_fdot_usefulness_docs.py`; no requiere migraciones, reinicio de servicios ni restauración de estado persistente porque la acción es documental y aislada.
