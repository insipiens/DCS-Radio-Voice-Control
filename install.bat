@echo off
setlocal
cd /d "%~dp0"
set "DRVC_CONFIG=%LOCALAPPDATA%\DCSRadioVoiceControl\config.json"
set "DRVC_FIRST_RUN=1"
if exist "%DRVC_CONFIG%" set "DRVC_FIRST_RUN=0"

call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
"%~dp0runtime\python.exe" "%~dp0tools\install.py" install %*
if errorlevel 1 exit /b %ERRORLEVEL%

if "%DRVC_FIRST_RUN%"=="0" exit /b 0

call "%~dp0configuration.bat" --start-after-save
set "DRVC_CONFIG_EXIT=%ERRORLEVEL%"
if "%DRVC_CONFIG_EXIT%"=="10" goto start_voice_control
if not "%DRVC_CONFIG_EXIT%"=="0" exit /b %DRVC_CONFIG_EXIT%
exit /b 0

:start_voice_control
call "%~dp0run.bat"
exit /b %ERRORLEVEL%
