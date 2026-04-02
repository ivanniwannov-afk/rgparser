@echo off
title Telegram Lead Monitoring System
color 0A

echo ================================================
echo  TELEGRAM LEAD MONITORING SYSTEM
echo ================================================
echo.

REM Check if venv exists
if not exist "venv\" (
    echo [ERROR] Virtual environment not found!
    echo Please run setup first.
    pause
    exit /b 1
)

echo [1/3] Starting Backend System...
echo.
start "Backend System" cmd /k "venv\Scripts\python.exe main.py"
timeout /t 3 /nobreak >nul

echo [2/3] Starting Dashboard...
echo.
start "Dashboard" cmd /k "venv\Scripts\streamlit.exe run dashboard.py --server.port 8501 --server.headless true"
timeout /t 3 /nobreak >nul

echo [3/3] Opening Dashboard in Browser...
timeout /t 5 /nobreak >nul
start http://localhost:8501

echo.
echo ================================================
echo  SYSTEM STARTED SUCCESSFULLY
echo ================================================
echo.
echo Backend:   Running in separate window
echo Dashboard: http://localhost:8501
echo.
echo To stop the system:
echo 1. Close this window
echo 2. Close "Backend System" window
echo 3. Close "Dashboard" window
echo.
echo Press any key to keep this window open...
pause >nul
