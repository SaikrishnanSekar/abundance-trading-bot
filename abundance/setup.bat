@echo off
rem One-command setup + verification. Stdlib only — nothing to pip install.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
echo Checking Python...
%PYCMD% -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'; print('Python OK:', sys.version.split()[0])" || goto :fail
echo Running smoke test...
%PYCMD% -m abundance.test_system || goto :fail
echo.
echo Setup complete. Schedule tasks with abundance\setup_schedule.bat (run as Administrator).
pause
exit /b 0
:fail
echo SETUP FAILED — see messages above.
pause
exit /b 1
