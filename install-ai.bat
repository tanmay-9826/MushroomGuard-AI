@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install.bat first to create the project environment.
  pause
  exit /b 1
)
echo Installing optional Ultralytics YOLO and its dependencies...
.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
if errorlevel 1 (
  echo AI installation failed. Check Python version, disk space and internet access.
  pause
  exit /b 1
)
echo Optional AI stack installed. No trained MushroomGuard model is included.
pause
