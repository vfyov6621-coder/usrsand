@echo off
chcp 65001 >nul
title Zaya UserBot — Builder

echo.
echo  ╔══════════════════════════════════════╗
echo  ║  Zaya UserBot — Builder (.exe)     ║
echo  ╚══════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo [1/3] Установка зависимостей сборки...
pip install pillow pyinstaller --quiet
echo   ✅ done

echo [2/3] Сборка .exe...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "ZayaUserBot_Setup" ^
    --add-data "background.png;." ^
    --icon "NONE" ^
    main.py
echo   ✅ done

echo [3/3] Очистка...
rmdir /s /q build 2>nul
del ZayaUserBot_Setup.spec 2>nul

echo.
echo  ╔══════════════════════════════════════╗
echo  ║  Готово!                            ║
echo  ║  Файл: dist\ZayaUserBot_Setup.exe  ║
echo  ╚══════════════════════════════════════╝
echo.
echo  Загрузите .exe в GitHub Releases:
echo  https://github.com/%REPO_OWNER%/%REPO_NAME%/releases/new
echo.
pause
