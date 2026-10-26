@echo off
REM Double-click to start Garage Games. The game screen opens in your browser.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 server.py %*) else (python server.py %*)
pause
