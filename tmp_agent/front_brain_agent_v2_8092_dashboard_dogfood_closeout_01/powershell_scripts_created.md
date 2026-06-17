# PowerShell Scripts Created

## Scripts generados para gestión del stack Brain Agent V2

| Script | Propósito | Estado |
|---|---|---|
| `scripts/brain/restart_brain_8091_agent_v2.ps1` | Reinicia Brain en puerto 8091 con Agent V2 | Creado |
| `scripts/brain/restart_dashboard_8092_agent_v2.ps1` | Reinicia Dashboard en puerto 8092, detecta zombies | Creado |
| `scripts/brain/probe_agent_v2_live.ps1` | Verifica endpoints Agent V2 en 8091 | Creado |
| `scripts/brain/probe_dashboard_8092_agent_v2.ps1` | Verifica Dashboard y detecta zombies en 8092 | Creado |
| `scripts/brain/start_brain_stack_agent_v2.ps1` | Inicia stack completo (8091 + 8092) | Creado |

## Características de los scripts

### Todos los scripts
- Aceptan parámetro `-Root` con default `C:\AI_VAULT_CANONICAL`
- Usan rutas absolutas
- Escriben logs a `tmp_agent/runtime`
- Muestran PID y línea de comando
- No cierran ventana sin mostrar error

### Script 8092 especial
- Detecta caso zombie:
  - netstat dice LISTENING
  - Get-Process no encuentra PID
  - Reporta WINDOWS_TCP_SOCKET_ZOMBIE
  - Recomienda reinicio Windows o netsh reset + reboot
- Solo inicia app canónica si puerto está libre:
  ```
  python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092 --log-level info
  ```

### Script 8091
- Inicia app canónica:
  ```
  python -m uvicorn brain_v9.main:app --host 127.0.0.1 --port 8091 --log-level info
  ```

## Veredicto
Scripts completados y listos para uso operacional.
