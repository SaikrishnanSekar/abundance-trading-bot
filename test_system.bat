@echo off
rem Smoke test - run anytime to confirm the journal pipeline is healthy.
rem Exits non-zero on the first failure.
cd /d C:\Users\saikr\Downloads\abundance-trading-bot
set PY=C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe

echo [1/4] Unit tests (journal core, outcomes, stats, gates, selection)...
%PY% -m unittest discover -s tests
if errorlevel 1 exit /b 1

echo [2/4] Outcome capture (idempotent dry pass)...
%PY% -m journal.capture_outcomes
if errorlevel 1 exit /b 1

echo [3/4] Weekly report...
%PY% -m journal.weekly_report
if errorlevel 1 exit /b 1

echo [4/4] Feedback loop (should report data-collection mode until N>=30)...
%PY% -m journal.feedback_loop
if errorlevel 1 exit /b 1

echo.
echo ALL SMOKE TESTS PASSED.
