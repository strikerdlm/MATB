@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Invoke-MatbWindows.ps1" -Action Verify %*
set "MATB_EXIT=%ERRORLEVEL%"
if not "%MATB_NO_PAUSE%"=="1" pause
exit /b %MATB_EXIT%
