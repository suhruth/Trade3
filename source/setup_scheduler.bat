@echo off
REM ---------------------------------------------------------------------------
REM Run this ONCE on a new machine to register the nightly bhavcopy archiver.
REM It self-locates run_archiver.bat next to this script, so there is nothing
REM to edit after copying the Trade3 folder. Double-click it, or run from a
REM terminal. Re-running is safe (/F overwrites the existing task).
REM
REM Default run time is 19:30 (after NSE publishes the full bhavcopy post-close).
REM To use a different time, pass it as HH:MM, e.g.:  setup_scheduler.bat 20:00
REM ---------------------------------------------------------------------------
setlocal
set "TASK=NSE Bhavcopy Archiver"
REM Note: do NOT name this TIME or DATE — those are reserved cmd variables.
set "STARTTIME=%~1"
if "%STARTTIME%"=="" set "STARTTIME=19:30"

schtasks /Create /SC DAILY /TN "%TASK%" /TR "\"%~dp0run_archiver.bat\"" /ST %STARTTIME% /F
if errorlevel 1 (
    echo.
    echo Failed to create the task. Try running this from a normal terminal.
) else (
    REM schtasks /Create has no flag for "run as soon as possible after a
    REM missed start" (StartWhenAvailable) -- without it, a trigger missed
    REM because the machine was off/logged-out at the scheduled time is
    REM just skipped, silently, until the next scheduled time. Enable it
    REM via PowerShell so a missed evening run fires as soon as you log on.
    powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 72); Set-ScheduledTask -TaskName '%TASK%' -Settings $s | Out-Null"
    echo.
    echo Task "%TASK%" registered to run daily at %STARTTIME% ^(while logged on; catches up automatically if the machine was off/logged-out at that time^).
    schtasks /Query /TN "%TASK%"
)
