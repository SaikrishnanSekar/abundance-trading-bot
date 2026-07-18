@echo off
rem 12-month baseline + ruleset backtest on real NSE data.
rem Uses Dhan history (1 call/symbol) when .env has DHAN creds; otherwise
rem downloads ~260 NSE bhavcopy files (first run only; later runs use cache).
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
%PYCMD% -m abundance.backtest --days 260 --fetch
pause
