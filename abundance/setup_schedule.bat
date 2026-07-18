@echo off
rem Windows Task Scheduler registration (run as Administrator).
rem Times are LOCAL machine time — set for IST (bhavcopy publishes ~18:30 IST).
setlocal
set "ROOT=%~dp0"
schtasks /Create /F /TN "Abundance\DailyScan" ^
  /TR "\"%ROOT%run_scan.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 19:15
schtasks /Create /F /TN "Abundance\JournalUpdate" ^
  /TR "\"%ROOT%run_journal_update.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 19:25
schtasks /Create /F /TN "Abundance\WeeklyReport" ^
  /TR "\"%ROOT%run_weekly_report.bat\"" /SC WEEKLY /D SAT /ST 10:00
echo Done. Verify with: schtasks /Query /TN "Abundance\DailyScan"
pause
