@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-launchers\scripts\Invoke-MatbWindows.ps1" -Action Diagnose
set "MATB_EXIT=%ERRORLEVEL%"
if not "%MATB_EXIT%"=="0" echo MATB action failed. See the message above and WINDOWS.md.
pause
exit /b %MATB_EXIT%

