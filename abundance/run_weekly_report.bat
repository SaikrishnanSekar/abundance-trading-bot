@echo off
rem Weekly rollup + evidence-gated feedback check (writes proposals only).
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYCMD=py -3"
where py >nul 2>nul || set "PYCMD=python"
%PYCMD% -m abundance.journal rollup
%PYCMD% -m abundance.feedback
