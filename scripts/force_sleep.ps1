param(
  [int]$IdleMinutes = 10,        # sleep once the user has been idle this long
  [string]$GiveUpAt = "23:59"    # HH:mm local — stop trying past this (respect active use)
)
# Idle-aware sleep. Called by the ForceSleep_* tasks. Instead of yanking the machine
# to sleep at a fixed instant (which would interrupt you mid-work), it waits until you've
# been idle for $IdleMinutes, then suspends. If you're still active by $GiveUpAt it exits
# WITHOUT sleeping — the next scheduled ForceSleep will try again. Wake events stay
# enabled so the nightly WakeToRun tasks can still wake the machine.

Add-Type @'
using System; using System.Runtime.InteropServices;
public class IdleT {
  [StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
  public static uint Seconds() {
    LASTINPUTINFO l = new LASTINPUTINFO(); l.cbSize = (uint)Marshal.SizeOf(l);
    GetLastInputInfo(ref l);
    return ((uint)Environment.TickCount - l.dwTime) / 1000;
  }
}
'@

$giveUp = [datetime]::ParseExact($GiveUpAt, 'HH:mm', $null)
if ($giveUp -lt (Get-Date)) { $giveUp = (Get-Date).Date.AddDays(1).Add($giveUp.TimeOfDay) }

$logDir = Join-Path $PSScriptRoot '..\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir 'force_sleep.log'
function Log($m) { "$([datetime]::Now.ToString('s')) $m" | Out-File -FilePath $log -Append -Encoding utf8 }

$thresh = $IdleMinutes * 60
Log "START idle>=${IdleMinutes}m, give up at $GiveUpAt"
while ((Get-Date) -lt $giveUp) {
  if ([IdleT]::Seconds() -ge $thresh) {
    Log "idle threshold met -> suspending"
    Add-Type -AssemblyName System.Windows.Forms
    # SetSuspendState(Suspend, Force=false, DisableWakeEvent=false) — sleeps; nightly
    # WakeToRun tasks can still wake it (wake events left enabled).
    [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false) | Out-Null
    Log "resumed (woke)"
    exit 0
  }
  Start-Sleep -Seconds 60
}
Log "gave up at $GiveUpAt (user still active) - not sleeping"
