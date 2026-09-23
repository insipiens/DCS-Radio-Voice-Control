@echo off
setlocal
cd /d "%~dp0"

echo Checking DCS Radio Voice Control components...
set "LogDir=%LOCALAPPDATA%\DCSRadioVoiceControl\logs"
if not exist "%LogDir%" mkdir "%LogDir%"
set "LogFile=%LogDir%\installer-components.log"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0maintenance.ps1" -Action reconcile > "%LogFile%" 2>&1
set "Result=%ERRORLEVEL%"
if not "%Result%"=="0" (
    echo Component setup failed. Details: "%LogFile%"
    type "%LogFile%"
    exit /b %Result%
)

exit /b 0
