@echo off
setlocal

set "APP_DIR=%~dp0"

cd /d "%APP_DIR%backend"

if not exist "venv\Scripts\python.exe" (
  py -3 -m venv venv
  if errorlevel 1 python -m venv venv
)

call "venv\Scripts\python.exe" -m pip install -r requirements.txt

start "Resume Review AI Backend" cmd /k ""%APP_DIR%backend\venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000"

cd /d "%APP_DIR%frontend"
call npm install

start "" "http://127.0.0.1:3000/"
call npm run dev -- --host 127.0.0.1 --port 3000

endlocal
