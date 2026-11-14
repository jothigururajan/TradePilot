@echo off
TITLE TradePilot NSE - Windows Task Scheduler Setup
ECHO ============================================================================
ECHO   REGISTERING DAILY 16:15 IST END-OF-DAY UPDATE TASK IN WINDOWS SCHEDULER
ECHO ============================================================================

SET APP_DIR=%~dp0
SET PYTHON_EXE=%APP_DIR%venv\Scripts\python.exe
SET SCRIPT_PATH=%APP_DIR%eod_auto_update.py

IF NOT EXIST "%PYTHON_EXE%" (
    ECHO [WARN] Virtual environment not found yet. Please run run_tradepilot.bat once first.
    PAUSE
    EXIT /B 1
)

schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /TN "TradePilot_NSE_EOD_Sync" /TR "\"%PYTHON_EXE%\" \"%SCRIPT_PATH%\"" /ST 16:15 /F
IF ERRORLEVEL 0 (
    ECHO [SUCCESS] Scheduled task "TradePilot_NSE_EOD_Sync" registered to run Mon-Fri at 16:15!
) ELSE (
    ECHO [ERROR] Could not register task. Try right-clicking and selecting "Run as Administrator".
)
PAUSE
