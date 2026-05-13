' AI_VAULT Services Auto-Start Installer
' Ejecutar este script como Administrador
' Crea una tarea programada para iniciar servicios automáticamente

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

strCommand = "powershell.exe -ExecutionPolicy Bypass -File " & _
             """C:\AI_VAULT\tmp_agent\services_manager.ps1""" & _
             " -Action start"

' Crear tarea programada
strTaskCmd = "schtasks /Create /F /TN ""AI_VAULT_AutoStart""" & _
             " /TR """ & strCommand & """" & _
             " /SC ONLOGON /DELAY 0000:30" & _
             " /RL HIGHEST"

WshShell.Run strTaskCmd, 0, True

MsgBox "✓ AI_VAULT Services Auto-Start instalado!" & vbCrLf & vbCrLf & _
       "Los servicios se iniciarán automáticamente 30 segundos después de iniciar sesión." & vbCrLf & vbCrLf & _
       "Para desinstalar, ejecuta: schtasks /Delete /TN AI_VAULT_AutoStart /F", _
       vbInformation, "AI_VAULT Services Installer"
