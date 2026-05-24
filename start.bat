@echo off
chcp 65001 >nul 2>&1
title sandusr v3.0

:: ═══════════════════════════════════════════
::  Log file: logs/log_DD_MM_HH-MM-SS.txt
:: ═══════════════════════════════════════════

:: Create logs folder
if not exist "logs" mkdir logs

:: Generate timestamp for filename
for /f "tokens=1-3 delims=/" %%d in ("%date%") do set DD=%%d
for /f "tokens=2-4 delims=/ " %%m in ("%date%") do set MM=%%m
for /f "tokens=3-4 delims=/ " %%y in ("%date%") do set YY=%%y
for /f "tokens=1-3 delims=:." %%h in ("%time%") do set HH=%%h
for /f "tokens=2-3 delims=:." %%mi in ("%time%") do set MI=%%mi
for /f "tokens=3 delims=:." %%s in ("%time%") do set SS=%%s

:: Pad with zero if needed
if "%HH:~1,1%"=="" set HH=0%HH%
if "%MI:~1,1%"=="" set MI=0%MI%
if "%SS:~1,1%"=="" set SS=0%SS%

set LOGFILE=logs\log_%DD%_%MM%_%HH%-%MI%-%SS%.txt

echo ========================================
echo    sandusr v3.0 - Starting...
echo ========================================
echo.
echo  [LOG] %LOGFILE%
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [%date% %time%] [ERROR] Python not found! >> "%LOGFILE%"
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

:: Install dependencies
echo [%date% %time%] [INFO] Installing dependencies... >> "%LOGFILE%"
echo [1/2] Installing dependencies...
python -m pip install --quiet pyrofork flask python-dotenv aiohttp requests python-socks[asyncio] 2>>"%LOGFILE%"

:: Start bot with output to both console and log file
echo [%date% %time%] [INFO] Starting userbot... >> "%LOGFILE%"
echo [2/2] Starting userbot...
echo.
echo ========================================
echo   Web panel: http://localhost:8080
echo   Log: %LOGFILE%
echo   Press Ctrl+C to stop
echo ========================================
echo.

:: Run python and tee output to log file
python main.py 2>&1 | tee "%LOGFILE%"

if %errorlevel% neq 0 (
    echo.
    echo [%date% %time%] [ERROR] Userbot crashed. >> "%LOGFILE%"
    echo [ERROR] Userbot crashed. Check your .env settings.
)
pause
