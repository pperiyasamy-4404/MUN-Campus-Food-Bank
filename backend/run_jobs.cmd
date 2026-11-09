@echo off
rem Runs the jobs script once (app/jobs.py). Windows Task Scheduler runs this every 15 minutes.
rem What each run did is added to jobs.log, next to this file. It has only numbers, nothing about a student.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m app.jobs >> jobs.log 2>&1
