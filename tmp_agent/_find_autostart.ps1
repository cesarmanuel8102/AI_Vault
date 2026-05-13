Get-ScheduledTask | Where-Object { $_.TaskName -match 'rain|atchdog|VAULT' } | Select-Object TaskName,TaskPath,State | Format-Table -AutoSize
