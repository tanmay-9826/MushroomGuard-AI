@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo   MushroomGuard AI - Windows Installation
echo ==============================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install Python 3.10+ from python.org and enable PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)
echo Updating pip...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :failed
echo Installing MushroomGuard AI requirements...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failed
echo Installing test tools...
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if errorlevel 1 goto :failed
echo.
echo Installation complete. Start the app using run.bat
pause
exit /b 0
:failed
echo.
echo Installation failed. Check the error above and confirm internet access is available for pip.
pause
exit /b 1
