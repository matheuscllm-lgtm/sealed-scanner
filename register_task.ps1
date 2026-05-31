# register_task.ps1 — registra o watchdog do scan unificado de selados no
# Windows Task Scheduler (a cada 15 min, sessão interativa p/ Chrome headful
# da Liga, sem empilhar instâncias, auto-ressuscita).
#
# Rode você mesmo (autoriza sob sua conta):
#   ! powershell -ExecutionPolicy Bypass -File "C:\Users\mathe\sealed-arbitrage-scanner\register_task.ps1"
#
# Para remover depois:
#   Unregister-ScheduledTask -TaskName SealedScannerWatchdog -Confirm:$false

$ErrorActionPreference = 'Stop'
$py  = 'C:\Users\mathe\AppData\Local\Programs\Python\Python312\python.exe'
$dir = 'C:\Users\mathe\sealed-arbitrage-scanner'
$taskName = 'SealedScannerWatchdog'

try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop; Write-Host 'removida tarefa antiga' }
catch { Write-Host 'nenhuma tarefa antiga' }

$action  = New-ScheduledTaskAction -Execute $py -Argument 'watchdog.py' -WorkingDirectory $dir
$start   = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'Keep-alive do scan unificado de selados TCG (Amazon+Liga+OLX) a cada 15min — auto-ressuscita.' | Out-Null

Write-Host 'TAREFA REGISTRADA:'
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object NextRunTime, LastTaskResult | Format-List
