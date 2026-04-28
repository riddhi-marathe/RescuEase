@echo off
cd /d "%~dp0"
echo ========================================
echo   RescuEase Crisis Management Server
echo ========================================
echo.

REM Check for virtual environment and activate
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call "venv\Scripts\activate.bat"
) else if exist "env\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call "env\Scripts\activate.bat"
) else (
    echo [INFO] No virtual environment found. Using system Python.
)

echo [INFO] Starting RescuEase Server...
echo [INFO] Open your browser to: http://localhost:5000
echo.

REM Try python first, fallback to py -3
python --version >nul 2>&1
if %errorlevel% equ 0 (
    python app.py
) else (
    echo [WARN] 'python' not found. Trying 'py -3'...
    py -3 --version >nul 2>&1
    if %errorlevel% equ 0 (
        py -3 app.py
    ) else (
        echo [ERROR] Python not found! Please install Python 3.
        pause
        exit /b 1
    )
)

echo.
echo [INFO] Server stopped.
pause

