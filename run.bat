@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
start "" /b "%~dp0runtime\pythonw.exe" -m dcs_radio_voice_control.launcher --tray %*
exit /b 0
