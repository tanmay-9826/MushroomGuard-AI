@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe app.py
if errorlevel 1 (
  echo MushroomGuard AI stopped with an error. Review the message above.
  pause
)
