@echo off
REM Status checker for Be[Sales] Intelligence System

echo ========================================
echo Be[Sales] Intelligence System
echo Status Checker
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
    echo ERROR: Virtual environment not found
    echo Please run start.bat first to set up the system
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run status checker
python check_status.py

pause
