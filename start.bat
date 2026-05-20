@echo off
chcp 65001 >nul 2>&1
title sandusr v3.0

echo ========================================
echo    sandusr v3.0 - Starting...
echo ========================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Install Python 3.10+ from https://python.org
    echo Make sure "Add Python to PATH" is checked.
    pause
    exit /b 1
)

:: Check .env
if not exist ".env" (
    echo [!] .env file not found. Creating from template...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [!] Edit .env and set API_ID, API_HASH, PHONE
        echo.
        notepad .env
        echo.
        echo After editing run start.bat again.
        pause
        exit /b 0
    ) else (
        echo [ERROR] .env.example not found. Download project again.
        pause
        exit /b 1
    )
)

:: Create folders
if not exist "logs" mkdir logs

:: Install dependencies
echo [1/2] Checking dependencies...
python -m pip install pyrofork flask python-dotenv aiohttp >nul 2>&1

:: Start
echo [2/2] Starting userbot...
echo.
echo ========================================
echo   Web panel: http://localhost:8080
echo   Press Ctrl+C to stop
echo ========================================
echo.

python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Userbot crashed. Check your .env settings.
)
pause
