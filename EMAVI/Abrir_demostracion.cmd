@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath node -ArgumentList 'construccion/serve_video.mjs' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:3128/
