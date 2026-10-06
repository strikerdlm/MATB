@echo off
setlocal
call "%~dp0..\Stop MATB.cmd" %*
exit /b %ERRORLEVEL%
