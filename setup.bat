@echo off
setlocal
cd /d "%~dp0"

echo Checking DCS Radio Voice Control components...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0maintenance.ps1" -Action reconcile
if errorlevel 1 exit /b %ERRORLEVEL%

exit /b 0
