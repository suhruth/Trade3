@echo off
REM Scaffold the journal folder for the current month (and next month near
REM month-end) from the templates. Portable: self-locates the repo via %~dp0.
REM Any args are passed through, e.g.:  new_month.bat --lookahead 7
setlocal
cd /d "%~dp0.."
where py >nul 2>nul && (py -3 source\new_month.py %*) || (python source\new_month.py %*)
