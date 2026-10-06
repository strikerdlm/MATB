@echo off
setlocal
call "%~dp0..\Diagnose MATB.cmd" %*
exit /b %ERRORLEVEL%
