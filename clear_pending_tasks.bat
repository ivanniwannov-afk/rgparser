@echo off
REM Clear pending tasks utility for Be[Sales] Intelligence System

echo ========================================
echo Be[Sales] Intelligence System
echo Clear Pending Tasks
echo ========================================
echo.
echo WARNING: This will delete all pending join tasks
echo and reset pending chats to unassigned state.
echo.
set /p confirm="Are you sure? (Y/N): "
if /i not "%confirm%"=="Y" (
    echo Operation cancelled.
    pause
    exit /b 0
)

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

REM Run clear pending tasks
python clear_pending_tasks.py

pause
