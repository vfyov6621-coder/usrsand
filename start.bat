@echo off
chcp 65001 >nul
title sandusr v3.0
color 0A

echo.
echo  ╔══════════════════════════════════════╗
echo  ║          sandusr v3.0               ║
echo  ║     Telegram Userbot                ║
echo  ╚══════════════════════════════════════╝
echo.

:: Создаём папку для логов
if not exist "logs" mkdir logs

:: Имя файла лога с датой и временем
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set "dt=%%a"
set "logfile=logs\sandusr_%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%.log"

echo  [INFO] Log: %logfile%
echo  [INFO] Starting...
echo.

:: Запуск бота с записью логов
python main.py 2>&1 > "%logfile%"

echo.
echo  [INFO] Bot stopped.
pause
