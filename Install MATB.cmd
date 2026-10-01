@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-launchers\scripts\Install-MatbWindows.ps1"
set "MATB_EXIT=%ERRORLEVEL%"
if not "%MATB_EXIT%"=="0" echo MATB action failed. See the message above and WINDOWS.md.
pause
exit /b %MATB_EXIT%

