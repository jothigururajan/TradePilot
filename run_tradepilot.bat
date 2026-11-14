@echo off
TITLE TradePilot NSE - Short-Term Stock Analysis Platform
ECHO ============================================================================
ECHO   TRADEPILOT NSE - ONE-CLICK WINDOWS LAUNCHER
ECHO ============================================================================

cd /d "%~dp0"

IF NOT EXIST "venv\Scripts\python.exe" (
    ECHO [1/3] Creating Python virtual environment ^(venv^)...
    python -m venv venv
    IF ERRORLEVEL 1 (
        ECHO [ERROR] Python 3.10+ was not found on your PATH. Please install Python from python.org and check "Add Python to PATH".
        PAUSE
        EXIT /B 1
    )
    ECHO [2/3] Installing TradePilot NSE dependencies...
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt
) ELSE (
    venv\Scripts\python.exe -c "import streamlit" >nul 2>&1
    IF ERRORLEVEL 1 (
        ECHO [FIX] Streamlit not found in venv. Installing dependencies...
        venv\Scripts\python.exe -m pip install -r requirements.txt
    )
)

ECHO [3/3] Starting TradePilot NSE Dashboard at http://localhost:8501 ...
venv\Scripts\python.exe -m streamlit run app.py --server.port=8501 --server.headless=false
PAUSE
