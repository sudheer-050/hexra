@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m hexra --rule
echo.
echo The app has closed. Messages from this run are saved in data\last_run.log
pause
