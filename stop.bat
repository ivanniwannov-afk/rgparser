@echo off
title Stop System
color 0C

echo ================================================
echo  STOPPING TELEGRAM LEAD MONITORING SYSTEM
echo ================================================
echo.

echo Stopping Python processes...
taskkill /F /FI "WINDOWTITLE eq Backend System*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Dashboard*" 2>nul
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM streamlit.exe /T 2>nul

echo.
echo ================================================
echo  SYSTEM STOPPED
echo ================================================
echo.
pause
