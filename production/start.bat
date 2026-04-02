@echo off
echo ================================================
echo Telegram Lead Monitoring System - Startup
echo ================================================
echo.

REM Set Python path
set PYTHON_PATH=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe

REM Check Python installation
"%PYTHON_PATH%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found at %PYTHON_PATH%
    echo Please check Python installation path.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('"%PYTHON_PATH%" --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%

REM Create venv if not exists
if not exist "venv" (
    echo Creating virtual environment...
    "%PYTHON_PATH%" -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully
)

REM Check if venv Python exists
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment is corrupted
    echo Deleting and recreating...
    rmdir /s /q venv
    "%PYTHON_PATH%" -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Install/update dependencies
echo Installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip
    pause
    exit /b 1
)

venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo Starting Telegram Lead Monitoring System...
echo.

REM Run main.py
venv\Scripts\python.exe main.py

pause
