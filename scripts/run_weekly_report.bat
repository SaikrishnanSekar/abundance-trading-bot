@echo off
rem Weekly rollup + evidence-gated feedback loop. Saturdays.
cd /d C:\Users\saikr\Downloads\abundance-trading-bot
C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe -m journal.weekly_report >> logs\journal_weekly.log 2>&1
C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe -m journal.feedback_loop >> logs\journal_weekly.log 2>&1
C:\Users\saikr\AppData\Local\Programs\Python\Python311\python.exe -m journal.dashboard >> logs\journal_weekly.log 2>&1
