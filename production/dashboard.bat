@echo off
REM Dashboard launcher for Be[Sales] Intelligence System

echo ========================================
echo Be[Sales] Intelligence System
echo Dashboard Launcher
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/upgrade streamlit if needed
echo Checking Streamlit installation...
pip show streamlit >nul 2>&1
if errorlevel 1 (
    echo Installing Streamlit...
    pip install streamlit
)

REM Launch dashboard
echo.
echo Starting dashboard...
echo Dashboard will open in your browser automatically
echo Press Ctrl+C to stop the dashboard
echo.
streamlit run dashboard.py

pause
