@echo off
echo ========================================
echo Telegram Lead Monitoring - Web Dashboard
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found
    echo Please run start.bat first to set up the environment
    pause
    exit /b 1
)

echo.
echo Starting Web Dashboard on http://localhost:8501
echo Press Ctrl+C to stop
echo.

venv\Scripts\python.exe -m streamlit run dashboard.py --server.port 8501 --server.address localhost

pause
