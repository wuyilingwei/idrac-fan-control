# Windows 自启动安装 — 计划任务 (开机触发) — PLAN §9.
#
# 用法 (管理员或当前用户 PowerShell):
#   powershell -ExecutionPolicy Bypass -File install-task.ps1 -InstallDir "C:\Path\To\install"
#
# 卸载:
#   Unregister-ScheduledTask -TaskName "idrac-fan-control" -Confirm:$false

param(
    [Parameter(Mandatory=$true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"

$InstallDir = (Resolve-Path $InstallDir).Path
$Bin = Join-Path $InstallDir "idrac-fan-control.exe"
$Config = Join-Path $InstallDir "config.json"

if (-not (Test-Path $Bin)) {
    Write-Error "ERROR: $Bin not found (run pyinstaller build.spec first)"
    exit 1
}

$TaskName = "idrac-fan-control"
$Description = "iDRAC Fan Control core service (auto-start at logon)"

# 删旧任务 (静默)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $Bin `
    -Argument "--config `"$Config`" --host 127.0.0.1 --port 8080" `
    -WorkingDirectory $InstallDir

# 登录时触发 (用户级,不需管理员);如要开机触发改为 New-ScheduledTaskTrigger -AtStartup
$trigger = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $Description `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal | Out-Null

Write-Host "Registered scheduled task '$TaskName'"
Write-Host "Start it now? (the task will run on next logon automatically)"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
