@echo off
rem Capture outcomes for recommendations whose 5-session window has closed.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
%PYCMD% -m abundance.journal update
