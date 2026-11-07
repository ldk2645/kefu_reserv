@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Follow README.md to install dependencies.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m app.main %*
if errorlevel 1 (
    echo Startup failed. Check README.md for recovery steps.
    pause
    exit /b 1
)
exit /b 0
