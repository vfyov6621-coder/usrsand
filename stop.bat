@echo off
chcp 65001 >nul 2>&1
title sandusr — Stop

echo   Stopping sandusr...
taskkill /f /im pythonw.exe >nul 2>&1

:: Kill python processes running sandusr
for /f "tokens=2 delims=," %%p in ('tasklist /fi "WINDOWTITLE eq sandusr*" /fo csv /nh ^| findstr /i "python"') do (
    set "pid=%%~p"
    if defined pid taskkill /f /pid !pid! >nul 2>&1
)

:: Also try by window title pattern
taskkill /f /fi "WINDOWTITLE eq sandusr*" >nul 2>&1

echo   Done.
timeout /t 2 >nul
exit /b 0