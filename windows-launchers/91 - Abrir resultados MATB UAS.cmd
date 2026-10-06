@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Invoke-MatbWindows.ps1" -Action Results %*
set "MATB_EXIT=%ERRORLEVEL%"
if not "%MATB_NO_PAUSE%"=="1" pause
exit /b %MATB_EXIT%
