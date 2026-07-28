# register_catalyst_tasks.ps1 — one-time setup of two LOCAL Windows scheduled tasks:
#   TradingBot\KeepAwake    — 08:30 Mon-Fri, wakes the machine and holds it awake to 13:00 IST
#   TradingBot\CatalystScan — every 10 min, 09:30-13:00 IST Mon-Fri (Claude headless catalyst research)
#
# Run once (no admin needed for your own-user tasks):
#   powershell -ExecutionPolicy Bypass -File scripts\register_catalyst_tasks.ps1
# Re-running is safe (-Force replaces). Remove later via: Unregister-ScheduledTask.

$repo = "C:\Users\saikr\Downloads\abundance-trading-bot"
$vbs  = "$repo\scripts\run_hidden.vbs"
$bat  = "$repo\scripts\run_catalyst_scan.bat"
$days = @('Monday','Tuesday','Wednesday','Thursday','Friday')

# ---------- Power: never sleep while plugged in (so all abundance cron tasks fire) ----------
# On AC = never sleep/hibernate; on battery keep the OS default (KeepAwake below still
# holds the 08:30-13:00 window on battery via WakeToRun). Change '0' to a minute value to
# re-enable AC sleep after N idle minutes (e.g. 120 = sleep after 2h idle plugged in).
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Write-Host "Power: AC sleep = never (plugged in won't sleep)."

# ---------- KeepAwake ----------
$kaAction  = New-ScheduledTaskAction -Execute "powershell.exe" `
              -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$repo\scripts\keep_awake.ps1`"" `
              -WorkingDirectory $repo
$kaTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 8:30am
$kaSettings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 5)
try {
  Register-ScheduledTask -TaskName "KeepAwake" -TaskPath "\TradingBot\" -Action $kaAction `
    -Trigger $kaTrigger -Settings $kaSettings -User $env:USERNAME -RunLevel Limited -Force -ErrorAction Stop | Out-Null
  Write-Host "KeepAwake registered OK"
} catch { Write-Host ("KeepAwake FAILED: " + $_.Exception.Message) }

# ---------- CatalystScan (every 10 min for 3.5h from 09:30 -> 13:00) ----------
$csAction  = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`" `"$bat`"" -WorkingDirectory $repo
$csTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 9:30am
$csTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At 9:30am `
    -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Hours 3 -Minutes 30)).Repetition
$csSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 9) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
try {
  Register-ScheduledTask -TaskName "CatalystScan" -TaskPath "\TradingBot\" -Action $csAction `
    -Trigger $csTrigger -Settings $csSettings -User $env:USERNAME -RunLevel Limited -Force -ErrorAction Stop | Out-Null
  Write-Host "CatalystScan registered OK"
} catch { Write-Host ("CatalystScan FAILED: " + $_.Exception.Message) }

Write-Host "`nRegistered tasks under \TradingBot\:"
Get-ScheduledTask -TaskPath "\TradingBot\" -TaskName "KeepAwake","CatalystScan" -ErrorAction SilentlyContinue |
  Format-Table TaskName, State -AutoSize
