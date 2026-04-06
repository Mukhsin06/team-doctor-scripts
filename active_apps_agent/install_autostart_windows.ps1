param(
  [string]$TaskName = "TeamDoctorActiveAppsAgent"
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $scriptDir 'run_windows.ps1'

if (-not (Test-Path $runScript)) {
  throw "run_windows.ps1 not found in $scriptDir"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "TeamDoctor Active Apps Agent Autostart" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "✅ Windows autostart installed"
Write-Host "Task: $TaskName"
Write-Host "Status: Get-ScheduledTask -TaskName $TaskName | Format-List"
