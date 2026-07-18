@echo off
rem 12-month baseline + ruleset backtest on real NSE bhavcopy data.
rem First run downloads ~260 daily files (a few minutes); later runs use cache.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
%PYCMD% -c "from abundance.data import prefetch; prefetch(260)"
%PYCMD% -m abundance.backtest --days 260
pause
