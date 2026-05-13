' START_ALL.vbs — DEPRECATED
' Use emergency_start.ps1 instead:
'
'   powershell -File "C:\AI_VAULT\tmp_agent\emergency_start.ps1"
'
' It starts Ollama + Brain V9 (which includes the dashboard
' at http://127.0.0.1:8090/ui).

MsgBox "This launcher is deprecated." & vbCrLf & vbCrLf & _
       "Use instead:" & vbCrLf & _
       "  powershell -File ""C:\AI_VAULT\tmp_agent\emergency_start.ps1""" & vbCrLf & vbCrLf & _
       "Dashboard is now built into Brain V9 at:" & vbCrLf & _
       "  http://127.0.0.1:8090/ui", _
       vbInformation, "AI_VAULT — DEPRECATED"
