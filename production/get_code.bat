@echo off
echo ================================================
echo Telegram Session Code Retrieval Utility
echo ================================================
echo.

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found
    echo Please run start.bat first to set up the environment
    pause
    exit /b 1
)

REM Run get_code.py
venv\Scripts\python.exe get_code.py

pause
