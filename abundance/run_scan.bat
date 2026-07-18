@echo off
rem Abundance daily scan — run after 19:00 IST (bhavcopy publishes ~18:30 IST)
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
%PYCMD% -m abundance.scan %*
