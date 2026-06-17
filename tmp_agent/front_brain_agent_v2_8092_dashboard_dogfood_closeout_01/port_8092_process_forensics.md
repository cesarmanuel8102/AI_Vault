# 8092 Process Forensics

## Diagnóstico del puerto 8092
- **PID reportado:** 183024
- **Estado netstat:** LISTENING (pero proceso muerto/zombie)
- **Verificación:** Get-Process -Id 183024 => "Cannot find a process with the process identifier 183024."
- **Tipo:** Proceso fantasma/zombie - el puerto quedó en LISTENING tras muerte del proceso

## Procesos Python activos encontrados
- python.exe PID 140768 Console (51,120 K)
- python.exe PID 123600 Console (139,032 K)  
- python.exe PID 57100 Console (13,480 K)
- Ninguno coincide con 183024

## Root cause
El proceso 8092 murió pero el handle del socket TCP en Windows no se liberó correctamente. Esto causa que:
1. netstat muestre LISTENING en 8092 con PID 183024
2. El proceso real no existe
3. El código canónico SÍ tiene /brain-dashboard/agent-v2/status
4. Pero el proceso vivo en 8092 ejecutaba código antiguo (sin la ruta)

## Solución requerida
Forzar cierre del socket o reiniciar el sistema. Como workaround operacional, usar 8091 como canonical para Agent V2 mientras se resuelve el zombie de 8092.
