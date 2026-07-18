@echo off
rem Daily outcome capture - run AFTER the nightly bhavcopy fetch (see
rem run_nightly_fetch.bat). Idempotent; safe to run any time.
cd /d C:\Users\saikr\Downloads\abundance-trading-bot
C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe -m journal.capture_outcomes >> logs\journal_update.log 2>&1
C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe -m journal.track >> logs\journal_update.log 2>&1
C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe -m journal.dashboard >> logs\journal_update.log 2>&1
