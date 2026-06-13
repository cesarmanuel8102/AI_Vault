# NEXT PROMPT RECOMMENDATION

## FRONT-BRAIN-DASHBOARD-STATUS-ENDPOINT-ROOTCAUSE-REPAIR-01

Objetivo: recuperar el endpoint live GET http://127.0.0.1:8092/brain-dashboard/status para que sirva el código corregido y responda HTTP 200 en menos de 5 segundos, sin tocar memoria semántica/FAISS, trading, B8 ni .env.

Criterios mínimos:
- Identificar con certeza el proceso 8092.
- No matar procesos desconocidos.
- Si el proceso viejo no puede detenerse por permisos, levantar dashboard en puerto alternativo controlado o documentar acción manual necesaria.
- Validar /brain-dashboard/status, /scheduler, /safety, /activity.
- Solo después de status live OK, reintentar ciclos de autonomía.
