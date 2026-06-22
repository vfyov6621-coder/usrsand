@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ═══════════════════════════════════════════════════════════════
::  sandusr v3.0 — Launcher with settings
::  Hotkey: create shortcut → properties → Shortcut key
:: ═══════════════════════════════════════════════════════════════

:: Defaults
set "CFG_AUTOSTART=0"
set "CFG_HIDDEN=0"
set "CFG_LOGS=1"

:: Load config
if exist "launcher.cfg" (
    for /f "usebackq tokens=1,* delims==" %%a in ("launcher.cfg") do (
        if "%%a"=="AUTOSTART" set "CFG_AUTOSTART=%%b"
        if "%%a"=="HIDDEN" set "CFG_HIDDEN=%%b"
        if "%%a"=="LOGS" set "CFG_LOGS=%%b"
    )
)

:: ═══ CLI args ═══
if "%~1"=="/auto" goto AUTO_START
if "%~1"=="/settings" goto SETTINGS
if "%~1"=="/hidden" goto DO_HIDDEN
if "%~1"=="/stop" goto DO_STOP

:: ═══ MAIN MENU ═══
:MAIN
cls
title sandusr v3.0
echo.
echo   ┌─────────────────────────────────┐
echo   │         sandusr v3.0            │
echo   └─────────────────────────────────┘
echo.
echo     [1]  Запустить
echo     [2]  Запустить скрыто
echo     [3]  Настройки
echo     [0]  Выход
echo.
choice /c 1230 /n >nul
if %errorlevel%==4 exit /b 0
if %errorlevel%==3 goto SETTINGS
if %errorlevel%==2 goto DO_HIDDEN
if %errorlevel%==1 goto DO_START

:: ═══ START NORMAL ═══
:DO_START
title sandusr v3.0
call :PRE_FLIGHT || exit /b 1
echo.
echo   ── Starting sandusr... ──
echo   Web: http://localhost:8080
echo   Logs: logs\DEBUG.log
echo   Ctrl+C — stop
echo.
if "%CFG_LOGS%"=="0" (
    set "SANDUSR_QUIET=1"
    echo   [Logs hidden]
    echo.
    python main.py >nul 2>&1
) else (
    set "SANDUSR_QUIET=0"
    python main.py
)
if %errorlevel% neq 0 (
    echo.
    echo   [ERROR] Crashed. Check logs\DEBUG.log
)
pause
exit /b %errorlevel%

:: ═══ START HIDDEN ═══
:DO_HIDDEN
call :PRE_FLIGHT || exit /b 1

:: Create VBS wrapper for silent launch
set "VBS=%~dp0_hidden.vbs"
echo Set objShell = CreateObject("WScript.Shell") > "!VBS!"
echo objShell.CurrentDirectory = "%~dp0" >> "!VBS!"
echo objShell.Run "cmd /c set SANDUSR_QUIET=1 ^&^& python main.py", 0, False >> "!VBS!"

:: Launch hidden via VBS
wscript.exe "!VBS!"
echo.
echo   sandusr started in background.
echo   Web: http://localhost:8080
echo   Run stop.bat to stop.
timeout /t 3 >nul
exit /b 0

:: ═══ AUTO-START (from Task Scheduler) ═══
:AUTO_START
call :PRE_FLIGHT || exit /b 1
if "%CFG_HIDDEN%"=="1" goto DO_HIDDEN
goto DO_START

:: ═══ STOP ═══
:DO_STOP
echo   Stopping sandusr...
taskkill /f /im pythonw.exe >nul 2>&1
for /f "tokens=2" %%p in ('tasklist /fi "WINDOWTITLE eq sandusr*" /nh ^| findstr /i python') do (
    taskkill /f /pid %%p >nul 2>&1
)
echo   Done.
timeout /t 2 >nul
exit /b 0

:: ═══════════════════════════════════════════════════════════════
::  SETTINGS MENU
:: ═══════════════════════════════════════════════════════════════
:SETTINGS
:SETTINGS_LOOP
cls
title sandusr — Настройки

:: Status labels
if "!CFG_AUTOSTART!"=="1" (
    set "S_AUTOSTART=ON "
) else (
    set "S_AUTOSTART=OFF"
)
if "!CFG_HIDDEN!"=="1" (
    set "S_HIDDEN=ON "
) else (
    set "S_HIDDEN=OFF"
)
if "!CFG_LOGS!"=="1" (
    set "S_LOGS=ON "
) else (
    set "S_LOGS=OFF"
)

echo.
echo   ┌──────── Настройки ────────┐
echo   │                           │
echo   │  [1] Автозапуск    !S_AUTOSTART!  │
echo   │  [2] Скрытый режим !S_HIDDEN!  │
echo   │  [3] Логи в консоли !S_LOGS!  │
echo   │                           │
echo   │  [4] Создать ярлык (Ctrl+Alt+S) │
echo   │  [5] Остановить бота       │
echo   │                           │
echo   │  [0] Назад                 │
echo   │                           │
echo   └───────────────────────────┘
echo.
choice /c 123450 /n >nul
set "SEL=%errorlevel%"

if "!SEL!"=="6" goto MAIN
if "!SEL!"=="5" goto DO_STOP
if "!SEL!"=="4" goto CREATE_SHORTCUT
if "!SEL!"=="3" goto TOGGLE_LOGS
if "!SEL!"=="2" goto TOGGLE_HIDDEN
if "!SEL!"=="1" goto TOGGLE_AUTOSTART
goto SETTINGS_LOOP

:: ── Toggle autostart ──
:TOGGLE_AUTOSTART
if "!CFG_AUTOSTART!"=="1" (
    :: Disable
    set "CFG_AUTOSTART=0"
    schtasks /delete /tn "sandusr" /f >nul 2>&1
    echo   Автозапуск: OFF
) else (
    :: Enable
    set "CFG_AUTOSTART=1"
    if "!CFG_HIDDEN!"=="1" (
        set "VBS=%~dp0_hidden.vbs"
        echo Set objShell = CreateObject("WScript.Shell") > "!VBS!"
        echo objShell.CurrentDirectory = "%~dp0" >> "!VBS!"
        echo objShell.Run "cmd /c set SANDUSR_QUIET=1 ^&^& python main.py", 0, False >> "!VBS!"
        schtasks /create /tn "sandusr" /tr "wscript.exe \"!VBS!\"" /sc onlogon /rl highest /f >nul 2>&1
    ) else (
        schtasks /create /tn "sandusr" /tr "\"%~dp0start.bat\" /auto" /sc onlogon /rl highest /f >nul 2>&1
    )
    echo   Автозапуск: ON
)
call :SAVE_CFG
timeout /t 1 >nul
goto SETTINGS_LOOP

:: ── Toggle hidden ──
:TOGGLE_HIDDEN
if "!CFG_HIDDEN!"=="1" (
    set "CFG_HIDDEN=0"
    echo   Скрытый режим: OFF
) else (
    set "CFG_HIDDEN=1"
    echo   Скрытый режим: ON
)
:: Re-apply autostart if enabled
if "!CFG_AUTOSTART!"=="1" (
    if "!CFG_HIDDEN!"=="1" (
        set "VBS=%~dp0_hidden.vbs"
        echo Set objShell = CreateObject("WScript.Shell") > "!VBS!"
        echo objShell.CurrentDirectory = "%~dp0" >> "!VBS!"
        echo objShell.Run "cmd /c set SANDUSR_QUIET=1 ^&^& python main.py", 0, False >> "!VBS!"
        schtasks /create /tn "sandusr" /tr "wscript.exe \"!VBS!\"" /sc onlogon /rl highest /f >nul 2>&1
    ) else (
        schtasks /create /tn "sandusr" /tr "\"%~dp0start.bat\" /auto" /sc onlogon /rl highest /f >nul 2>&1
    )
)
call :SAVE_CFG
timeout /t 1 >nul
goto SETTINGS_LOOP

:: ── Toggle logs ──
:TOGGLE_LOGS
if "!CFG_LOGS!"=="1" (
    set "CFG_LOGS=0"
    echo   Логи в консоли: OFF
) else (
    set "CFG_LOGS=1"
    echo   Логи в консоли: ON
)
call :SAVE_CFG
timeout /t 1 >nul
goto SETTINGS_LOOP

:: ── Create shortcut with hotkey ──
:CREATE_SHORTCUT
echo.
echo   Создаю ярлык на рабочем столе...
set "LNK=%USERPROFILE%\Desktop\sandusr.lnk"
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s = $ws.CreateShortcut('%LNK%');" ^
    "$s.TargetPath = '%~dp0start.bat';" ^
    "$s.Arguments = '/settings';" ^
    "$s.WorkingDirectory = '%~dp0%';" ^
    "$s.Description = 'sandusr settings';" ^
    "$s.Save()"
if exist "!LNK!" (
    echo.
    echo   Ярлык создан: %LNK%
    echo.
    echo   Чтобы поставить горячую клавишу:
    echo     1. ПКМ по ярлыку → Свойства
    echo     2. Поле "Быстрый вызов" → нажми Ctrl+Alt+S
    echo     3. OK
    echo.
) else (
    echo   [ERROR] Не удалось создать ярлык.
)
pause
goto SETTINGS_LOOP

:: ═══════════════════════════════════════════════════════════════
::  HELPERS
:: ═══════════════════════════════════════════════════════════════

:SAVE_CFG
(
    echo AUTOSTART=!CFG_AUTOSTART!
    echo HIDDEN=!CFG_HIDDEN!
    echo LOGS=!CFG_LOGS!
) > "launcher.cfg"
exit /b 0

:PRE_FLIGHT
:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python not found!
    echo   Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
:: Create logs dir
if not exist "logs" mkdir logs
:: Check .env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo   [!] .env создан. Открываю для редактирования...
        notepad .env
        echo   После редактирования запусти start.bat снова.
        pause
        exit /b 1
    ) else (
        echo   [ERROR] .env и .env.example не найдены.
        pause
        exit /b 1
    )
)
:: Install deps (quiet)
echo   Checking dependencies...
python -m pip install --quiet pyrofork flask python-dotenv aiohttp requests python-socks[asyncio] 2>nul
exit /b 0