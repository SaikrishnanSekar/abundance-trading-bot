# keep_awake.ps1 — hold the machine awake through market hours so the scheduled
# tasks (KotakFeed, MultiStrategyScan, CatalystScan, ...) actually run. Started at
# 08:30 IST by Task: TradingBot\KeepAwake (with WakeToRun, so it also wakes a
# sleeping machine), holds until 13:00 IST, then releases the wake lock.
#
# Uses SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) — the system-
# required flag prevents sleep even in a headless (session 0) scheduled-task run.

Add-Type -Namespace Win32 -Name Power -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
'@

$ES_CONTINUOUS       = [uint32]'0x80000000'
$ES_SYSTEM_REQUIRED  = [uint32]'0x00000001'
$ES_DISPLAY_REQUIRED = [uint32]'0x00000002'
$keepFlags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED

$logDir = Join-Path $PSScriptRoot '..\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir 'keep_awake.log'
function Log($m) { "$([DateTime]::Now.ToString('s')) $m" | Out-File -FilePath $log -Append -Encoding utf8 }

# Hold until 16:10 local (machine timezone is Asia/Calcutta = IST) — covers the full
# market + afternoon scan window (MultiStrategyScan ends 16:00). ForceSleep_Afternoon
# then sleeps the machine at 16:15. On AC this is redundant with never-sleep; it's the
# battery / wake-from-sleep safety net.
$end = (Get-Date).Date.AddHours(16).AddMinutes(10)
Log "keep-awake START, holding until $end"
[Win32.Power]::SetThreadExecutionState($keepFlags) | Out-Null

while ((Get-Date) -lt $end) {
    Start-Sleep -Seconds 60
    # Re-assert every minute in case anything cleared it.
    [Win32.Power]::SetThreadExecutionState($keepFlags) | Out-Null
}

# Release — let normal power policy resume.
[Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
Log "keep-awake RELEASED at $([DateTime]::Now.ToString('s'))"
