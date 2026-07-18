@echo off
rem Smoke test — safe to run anytime; uses a temporary journal DB.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
%PYCMD% -m abundance.test_system
pause
