@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Open Launch BlamHammer.cmd.
pause
exit /b 0
:failed
echo Setup failed. Check the error above. Python 3.14 x64 is recommended.
pause
exit /b 1
