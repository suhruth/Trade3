@echo off
REM Nightly wrapper, launched by Task Scheduler. Three jobs, in order:
REM   1. new_month.py        — ensure the journal month folder exists
REM   2. archive_bhavcopy.py — download today's NSE full security bhavcopy
REM   3. archive_indices.py  — download today's NSE all-indices close (sector data)
REM Portable: self-locates the repo via %~dp0 (...\source\); no hardcoded paths.
REM All output is appended to logs\archiver.log.
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs

REM Pick a Python once: prefer the py launcher, fall back to python on PATH.
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

echo ===== %date% %time% ===== >> logs\archiver.log
echo [new_month] >> logs\archiver.log
%PY% source\new_month.py >> logs\archiver.log 2>&1
echo [archive_bhavcopy] >> logs\archiver.log
%PY% source\archive_bhavcopy.py >> logs\archiver.log 2>&1
echo [archive_indices] >> logs\archiver.log
%PY% source\archive_indices.py >> logs\archiver.log 2>&1
echo(>> logs\archiver.log
