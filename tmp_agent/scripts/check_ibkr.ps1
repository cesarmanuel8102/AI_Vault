Get-Process | Where-Object { $_.ProcessName -match 'java|ibgateway|tws' } | Select-Object ProcessName, Id, StartTime | Format-Table -AutoSize
