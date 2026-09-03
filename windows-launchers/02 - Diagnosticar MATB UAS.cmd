@echo off
setlocal
where pwsh.exe >nul 2>&1
if errorlevel 1 (
  echo PowerShell 7 is required. Install it and run this shortcut again.
  pause
  exit /b 1
)
pwsh.exe -NoLogo -NoProfile -File "%~dp0scripts\Test-MatbUasEnvironment.ps1"
set "MATB_EXIT=%ERRORLEVEL%"
pause
exit /b %MATB_EXIT%
