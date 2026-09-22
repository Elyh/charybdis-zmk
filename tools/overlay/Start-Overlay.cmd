@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto fail
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
start "" .venv\Scripts\pythonw.exe overlay.py
exit /b
:fail
echo Install Python 3.12 or newer from python.org, then try again.
pause
