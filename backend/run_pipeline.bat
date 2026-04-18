@echo off
REM Run preprocess, anomaly detection, and forecast on Windows
setlocal
cd /d %~dp0

echo [1/3] Preprocess sample data
"%~dp0..\venv_py\Scripts\python.exe" "%~dp0preprocess.py"
if %errorlevel% neq 0 (
  echo Preprocess failed
  exit /b 1
)

echo [2/3] Start Flask to ensure tables exist
REM Optional quick health check
echo [3/3] Anomaly detection and forecast are API-triggered from UI
echo Done.
endlocal

