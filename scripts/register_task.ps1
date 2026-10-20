<#
.SYNOPSIS
  Creates (or replaces) the Windows Task Scheduler task that runs the pipeline daily.

.DESCRIPTION
  Review before running. The task:
    * runs scripts\run_pipeline.ps1 daily at the given local time (Windows time zone);
    * runs only while you are logged on, so no Windows password is stored;
    * never starts a second instance while one is running ("Do not start a new instance");
    * stops after 1 hour if something hangs.
  Disable or remove it in Task Scheduler, or with the commands at the end of docs\SCHEDULING.md.

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\register_task.ps1 -At 06:00
#>
param(
    [string]$TaskName = "GlobalEconomicDataPipeline",
    [string]$At = "06:00"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\run_pipeline.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Global Economic Data Pipeline: daily World Bank load (scripts\run_pipeline.ps1)" -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
"Next run: " + (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime
