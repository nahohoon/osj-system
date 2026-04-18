@echo off
chcp 65001 > nul
echo =============================================
echo  Osungjeongong Smart MFG System
echo  Startup Script v1.0
echo =============================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing packages...
pip install -r requirements.txt --quiet

echo.
echo Starting server... (http://localhost:5001)
echo Press Ctrl+C to stop.
echo.

start "OSJ_SERVER" cmd /k python app.py
timeout /t 3 >nul
start "" http://localhost:5001