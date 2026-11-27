# ============================================================
# Aqing v1.34 - Windows scheduled tasks for broadcast
#
#   AqingBroadcast : daily 08:00 + 18:00 -> _broadcast_verified.sh once
#   AqingCatchup   : AtLogOn (after login) -> _broadcast_verified.sh catchup
#                    (idempotent, 6h window, only fills a missed slot)
#
# Chain: Task Scheduler -> wsl.exe -u root -> host-layer verify script
#   (confirms full download on device + auto-retry + keepalive + done marker)
#
# IMPORTANT v1.34: AqingBroadcast has StartWhenAvailable DISABLED.
#   Missed-slot catch-up is now the ONLY job of AqingCatchup (6h window,
#   explicit slot, done-marker idempotency). Enabling StartWhenAvailable
#   again would double-fire on boot with no window -> do NOT re-enable.
#
# NOTE: WSL distro is per-user. Tasks run as current interactive user,
#   LogonType=Interactive, RunLevel=Limited (NO admin needed).
#   Only fire when user is logged in (WSL per-user binding). No stored pwd.
#   "PC off / not logged in" -> fires at next login, catch-up only within 6h.
#
# Rollback: Disable-ScheduledTask / Unregister-ScheduledTask anytime.
#   Does NOT touch gateway service / image 1.33 (host-layer only).
#
# Usage (PowerShell here; PS5.1 cannot read UTF-8 BOM-less CJK, ASCII-only;
#   invoke with -ExecutionPolicy Bypass):
#   register: powershell -NoProfile -ExecutionPolicy Bypass -File .\_register_broadcast_task.ps1 -Scope catchup -Action register
#   query  : ... -Scope all  -Action query
#   disable: ... -Scope catchup -Action disable
#   enable : ... -Scope catchup -Action enable
#   remove : ... -Scope catchup -Action remove
#   probe  : ... -Scope all  -Action probe   (no-sound link check)
# Scope: daily | catchup | all (default all)
# ============================================================
param(
    [ValidateSet('daily','catchup','all')]
    [string]$Scope = 'all',
    [ValidateSet('register','query','disable','enable','remove','probe')]
    [string]$Action = 'query'
)

$DailyName   = 'AqingBroadcast'
$CatchupName = 'AqingCatchup'
$TaskPath    = '\'
$WSL         = 'C:\Windows\system32\wsl.exe'
$Script      = '/opt/folotoy/gateway/_broadcast_verified.sh'
$ArgOnce     = "-u root bash $Script once"
$ArgCatchup  = "-u root bash $Script catchup"
$ArgProbe    = "-u root bash $Script probe"
$User        = [Security.Principal.WindowsIdentity]::GetCurrent().Name

function Get-Task([string]$n) { Get-ScheduledTask -TaskName $n -TaskPath $TaskPath -ErrorAction SilentlyContinue }
function Get-Info([string]$n) { $t=Get-Task $n; if($t){ $i=$t|Get-ScheduledTaskInfo; Write-Output "TASK: $($t.TaskPath)$($t.TaskName) | State=$($t.State)"; Write-Output "  Triggers : $((($t.Triggers | ForEach-Object { $_.CimClass.CimClassName+':'+$_.StartBoundary }) -join ', '))"; Write-Output "  Action   : $($t.Actions[0].Execute) $($t.Actions[0].Arguments)"; Write-Output "  RunAs    : $($t.Principal.UserId) / $($t.Principal.LogonType) / $($t.Principal.RunLevel)"; Write-Output "  StartWhenAvailable=$($t.Settings.StartWhenAvailable) Multiple=$($t.Settings.MultipleInstances)"; Write-Output "  LastRun  : $($i.LastRunTime)  LastResult=$($i.LastTaskResult)"; Write-Output "  NextRun  : $($i.NextRunTime)" } else { Write-Output "NOT_FOUND: $n" } }

function Register-Daily {
    if (Get-Task $DailyName) { Write-Output "ALREADY_EXISTS: $DailyName"; return }
    $t1 = New-ScheduledTaskTrigger -Daily -At '08:00'
    $t2 = New-ScheduledTaskTrigger -Daily -At '18:00'
    $act = New-ScheduledTaskAction -Execute $WSL -Argument $ArgOnce
    $prin = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
    $set  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 12) -MultipleInstances IgnoreNew
    # NOTE: deliberately NO -StartWhenAvailable (v1.34: catchup owns missed slots)
    Register-ScheduledTask -TaskName $DailyName -TaskPath $TaskPath -Action $act -Trigger @($t1,$t2) -Principal $prin -Settings $set -Force | Out-Null
    Write-Output "REGISTERED: $DailyName (daily 08:00+18:00, StartWhenAvailable=FALSE)"
    # If it already existed with StartWhenAvailable=TRUE from v1.33, normalize it here:
    $t = Get-Task $DailyName
    if ($t) { $t.Settings.StartWhenAvailable=$false; Set-ScheduledTask -TaskName $DailyName -TaskPath $TaskPath -Settings $t.Settings | Out-Null; Write-Output "  normalized StartWhenAvailable=FALSE" }
}
function Register-Catchup {
    if (Get-Task $CatchupName) { Write-Output "ALREADY_EXISTS: $CatchupName"; return }
    $tr = New-ScheduledTaskTrigger -AtLogOn -User $User
    # NOTE: AtLogOn Delay must be ISO-8601 string (PT2M). A TimeSpan writes
    #   invalid task XML ("Delay:00:02:00") and Register-ScheduledTask fails.
    $tr.Delay = 'PT2M'
    $act = New-ScheduledTaskAction -Execute $WSL -Argument $ArgCatchup
    $prin = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
    $set  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $CatchupName -TaskPath $TaskPath -Action $act -Trigger $tr -Principal $prin -Settings $set -Force | Out-Null
    Write-Output "REGISTERED: $CatchupName (AtLogOn + 2min delay -> catchup, 6h window, idempotent)"
}
function Do-Simple([string]$n, [string]$a) {
    $t = Get-Task $n
    if (-not $t) { Write-Output "NOT_FOUND: $n"; return }
    switch ($a) {
        'disable' { Disable-ScheduledTask -TaskName $n -TaskPath $TaskPath | Out-Null; Write-Output "DISABLED: $n" }
        'enable'  { Enable-ScheduledTask  -TaskName $n -TaskPath $TaskPath | Out-Null; Write-Output "ENABLED: $n" }
        'remove'  { Unregister-ScheduledTask -TaskName $n -TaskPath $TaskPath -Confirm:$false; Write-Output "REMOVED: $n (gateway/image untouched)" }
    }
}

switch ($Action) {
    'register' {
        if ($Scope -eq 'daily'   -or $Scope -eq 'all') { Register-Daily }
        if ($Scope -eq 'catchup' -or $Scope -eq 'all') { Register-Catchup }
    }
    'query' {
        if ($Scope -eq 'daily'   -or $Scope -eq 'all') { Get-Info $DailyName }
        if ($Scope -eq 'catchup' -or $Scope -eq 'all') { Get-Info $CatchupName }
    }
    { $_ -in @('disable','enable','remove') } {
        if ($Scope -eq 'daily'   -or $Scope -eq 'all') { Do-Simple $DailyName $Action }
        if ($Scope -eq 'catchup' -or $Scope -eq 'all') { Do-Simple $CatchupName $Action }
    }
    'probe' {
        Write-Output "PROBE: $WSL $ArgProbe"
        & $WSL -u root bash $Script probe
        Write-Output "PROBE_EXIT=$LASTEXITCODE"
        Write-Output "--- catchup dry (no push/no sound) ---"
        & $WSL -u root bash $Script catchup dry
        Write-Output "CATCHUP_DRY_EXIT=$LASTEXITCODE"
    }
}
