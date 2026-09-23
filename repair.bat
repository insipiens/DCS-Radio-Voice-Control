@echo off
setlocal
cd /d "%~dp0"

echo Checking DCS Radio Voice Control components...
call "%~dp0setup.bat"
if errorlevel 1 goto failed

echo Checking the DCS radio-menu integration...
"%~dp0runtime\python.exe" "%~dp0tools\install.py" install
if errorlevel 1 goto failed

echo.
echo DCS Radio Voice Control repair is complete.
pause
exit /b 0

:failed
set "DRVC_ERROR=%ERRORLEVEL%"
echo.
echo Repair stopped safely. Review the error above; no safety check was bypassed.
pause
exit /b %DRVC_ERROR%
