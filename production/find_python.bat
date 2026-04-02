@echo off
echo Searching for Python installation...
echo.

REM Search in common locations
echo Checking C:\Python*
dir C:\Python* /b 2>nul
echo.

echo Checking C:\Program Files\Python*
dir "C:\Program Files\Python*" /b 2>nul
echo.

echo Checking C:\Program Files (x86)\Python*
dir "C:\Program Files (x86)\Python*" /b 2>nul
echo.

echo Checking %LOCALAPPDATA%\Programs\Python
dir "%LOCALAPPDATA%\Programs\Python" /b 2>nul
echo.

echo Checking %APPDATA%\Local\Programs\Python
dir "%APPDATA%\Local\Programs\Python" /b 2>nul
echo.

echo Checking C:\Users\*\AppData\Local\Programs\Python
dir "C:\Users\*\AppData\Local\Programs\Python" /b /s 2>nul
echo.

echo Searching for python.exe in all drives...
where /R C:\ python.exe 2>nul
echo.

echo Checking Windows Registry...
reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Python" /s 2>nul
reg query "HKEY_CURRENT_USER\SOFTWARE\Python" /s 2>nul
echo.

echo Done! Copy the path you found above.
pause
