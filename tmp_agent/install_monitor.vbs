Set WshShell = CreateObject("WScript.Shell")

' Crear accion para el monitor
strMonitorCmd = "pythonw.exe C:\AI_VAULT\tmp_agent\monitor.py"

' Crear tarea programada para el monitor
strTaskCmd = "schtasks /Create /F /TN ""AI_VAULT_Monitor""" & _
             " /TR """ & strMonitorCmd & """" & _
             " /SC ONLOGON /DELAY 0000:60 /RL HIGHEST"

WshShell.Run strTaskCmd, 0, True

MsgBox "✓ AI_VAULT Services Monitor instalado!" & vbCrLf & vbCrLf & _
       "Monitor se ejecutara 60 segundos despues de iniciar sesion." & vbCrLf & _
       "Mantiene Brain V9 y Dashboard siempre activos." & vbCrLf & vbCrLf & _
       "Para verificar: schtasks /Query /TN AI_VAULT_Monitor", _
       vbInformation, "AI_VAULT Monitor Installer"
