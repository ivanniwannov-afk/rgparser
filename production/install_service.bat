@echo off
echo ================================================
echo Telegram Lead Monitoring - Service Installation
echo ================================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: This script requires administrator privileges
    echo Please right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo This script will install the system as a Windows service using NSSM.
echo.
echo NSSM (Non-Sucking Service Manager) will be downloaded if not present.
echo.
pause

REM Check if NSSM exists
if not exist "nssm.exe" (
    echo Downloading NSSM...
    echo Please download NSSM from: https://nssm.cc/download
    echo Extract nssm.exe to this directory and run this script again.
    pause
    exit /b 1
)

REM Get current directory
set CURRENT_DIR=%cd%

REM Install service
echo Installing service...
nssm install TelegramLeadMonitoring "%CURRENT_DIR%\venv\Scripts\python.exe" "%CURRENT_DIR%\main.py"
nssm set TelegramLeadMonitoring AppDirectory "%CURRENT_DIR%"
nssm set TelegramLeadMonitoring DisplayName "Telegram Lead Monitoring System"
nssm set TelegramLeadMonitoring Description "Automated Telegram chat monitoring and lead qualification system"
nssm set TelegramLeadMonitoring Start SERVICE_AUTO_START

echo.
echo Service installed successfully!
echo.
echo To start the service: nssm start TelegramLeadMonitoring
echo To stop the service: nssm stop TelegramLeadMonitoring
echo To remove the service: nssm remove TelegramLeadMonitoring confirm
echo.
pause
