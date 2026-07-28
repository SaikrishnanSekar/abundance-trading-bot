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
powercfg /hibernate off                                    # so forced-sleep suspends (not hibernates)
powercfg /setacvalueindex scheme_current sub_sleep bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d 1  # allow wake timers
powercfg /setactive scheme_current
Write-Host "Power: AC sleep = never (idle); hibernate off; wake timers allowed (for nightly WakeToRun)."

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

# ---------- Sleep/wake cycle: sleep after the afternoon cron, wake for nightly ----------
# Let the 20:00 / 20:30 nightly journal tasks wake the machine from the afternoon sleep.
foreach ($tn in @('NightlyHistoryFetch','JournalUpdate')) {
  $tk = Get-ScheduledTask -TaskPath "\TradingBot\" -TaskName $tn -ErrorAction SilentlyContinue
  if ($tk) {
    $tk.Settings.WakeToRun = $true
    $tk.Settings.StartWhenAvailable = $true
    try { Set-ScheduledTask -InputObject $tk -ErrorAction Stop | Out-Null; Write-Host "$tn -> WakeToRun ON" }
    catch { Write-Host ("$tn WakeToRun FAILED: " + $_.Exception.Message) }
  } else { Write-Host "$tn not found (skip WakeToRun)" }
}

# Two forced-sleep tasks — IDLE-AWARE (force_sleep.ps1): they start at the trigger time
# but only suspend once you've been idle >=10 min, and give up (don't sleep) if you're
# still active by their give-up time — so they never yank the machine mid-work. Run DAILY
# so weekends sleep too. Wake events stay enabled so nightly WakeToRun still wakes it.
$sleepSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                   -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 8)
foreach ($s in @(@{n='ForceSleep_Afternoon'; t='4:15pm'; give='19:45'}, @{n='ForceSleep_Night'; t='9:00pm'; give='23:30'})) {
  $act = New-ScheduledTaskAction -Execute "powershell.exe" `
           -Argument ("-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$repo\scripts\force_sleep.ps1`" -IdleMinutes 10 -GiveUpAt " + $s.give) `
           -WorkingDirectory $repo
  try {
    Register-ScheduledTask -TaskName $s.n -TaskPath "\TradingBot\" -Action $act `
      -Trigger (New-ScheduledTaskTrigger -Daily -At $s.t) `
      -Settings $sleepSettings -User $env:USERNAME -RunLevel Limited -Force -ErrorAction Stop | Out-Null
    Write-Host ($s.n + " registered OK (" + $s.t + " daily, idle-aware, give up " + $s.give + ")")
  } catch { Write-Host ($s.n + " FAILED: " + $_.Exception.Message) }
}

Write-Host "`nRegistered tasks under \TradingBot\:"
Get-ScheduledTask -TaskPath "\TradingBot\" -TaskName "KeepAwake","CatalystScan","ForceSleep_Afternoon","ForceSleep_Night" -ErrorAction SilentlyContinue |
  Format-Table TaskName, State -AutoSize
Write-Host "Power cycle: awake 08:30-16:15, idle-sleep, wake 20:00/20:30 for nightly journal, idle-sleep after 21:00."
Write-Host "Sleeps run DAILY (weekends too); KeepAwake+CatalystScan are Mon-Fri only."
