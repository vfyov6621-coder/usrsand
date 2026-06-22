@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ═══════════════════════════════════════════════════════════════
::  sandusr v3.0 — Launcher with settings + VPN
:: ═══════════════════════════════════════════════════════════════

:: Defaults
set "CFG_AUTOSTART=0"
set "CFG_HIDDEN=0"
set "CFG_LOGS=1"
set "VPN_ENABLED=0"
set "VPN_SOCKS_PORT=10808"
set "VPN_HTTP_PORT=10809"
set "VPN_AUTO=0"

:: Load config
if exist "launcher.cfg" (
    for /f "usebackq tokens=1,* delims==" %%a in ("launcher.cfg") do (
        if "%%a"=="AUTOSTART" set "CFG_AUTOSTART=%%b"
        if "%%a"=="HIDDEN" set "CFG_HIDDEN=%%b"
        if "%%a"=="LOGS" set "CFG_LOGS=%%b"
        if "%%a"=="VPN_ENABLED" set "VPN_ENABLED=%%b"
        if "%%a"=="VPN_SOCKS_PORT" set "VPN_SOCKS_PORT=%%b"
        if "%%a"=="VPN_HTTP_PORT" set "VPN_HTTP_PORT=%%b"
        if "%%a"=="VPN_AUTO" set "VPN_AUTO=%%b"
    )
)

:: ═══ CLI args ═══
if "%~1"=="/auto" goto AUTO_START
if "%~1"=="/settings" goto SETTINGS
if "%~1"=="/hidden" goto DO_HIDDEN
if "%~1"=="/stop" goto DO_STOP
if "%~1"=="/vpn" goto VPN_MENU

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

:: Auto-connect VPN
if "!VPN_ENABLED!"=="1" if "!VPN_AUTO!"=="1" (
    echo.
    echo   ── Подключаю VPN... ──
    python vpn_manager.py connect
    if !errorlevel! neq 0 (
        echo.
        echo   [!] VPN не подключён. Запускаю без VPN...
        echo.
        timeout /t 2 >nul
    ) else (
        echo.
    )
)

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

:: Disconnect VPN after bot stops
if "!VPN_ENABLED!"=="1" if "!VPN_AUTO!"=="1" (
    echo.
    echo   ── Отключаю VPN... ──
    python vpn_manager.py disconnect >nul 2>&1
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

:: Auto-connect VPN before hidden start
if "!VPN_ENABLED!"=="1" if "!VPN_AUTO!"=="1" (
    echo   Подключаю VPN...
    python vpn_manager.py connect >nul 2>&1
    timeout /t 2 >nul
)

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
if "!VPN_ENABLED!"=="1" echo   VPN: connected (auto)
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
:: Also stop VPN
python vpn_manager.py disconnect >nul 2>&1
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
if "!CFG_AUTOSTART!"=="1" (set "S_AUTOSTART=ON ") else (set "S_AUTOSTART=OFF")
if "!CFG_HIDDEN!"=="1" (set "S_HIDDEN=ON ") else (set "S_HIDDEN=OFF")
if "!CFG_LOGS!"=="1" (set "S_LOGS=ON ") else (set "S_LOGS=OFF")
if "!VPN_ENABLED!"=="1" (set "S_VPN=ON ") else (set "S_VPN=OFF")

echo.
echo   ┌──────── Настройки ─────────────┐
echo   │                                │
echo   │  [1] Автозапуск     !S_AUTOSTART!   │
echo   │  [2] Скрытый режим  !S_HIDDEN!   │
echo   │  [3] Логи в консоли !S_LOGS!   │
echo   │                                │
echo   │  [4] VPN            !S_VPN!   │
echo   │                                │
echo   │  [5] Создать ярлык (Ctrl+Alt+S) │
echo   │  [6] Остановить бота           │
echo   │                                │
echo   │  [0] Назад                     │
echo   │                                │
echo   └────────────────────────────────┘
echo.
choice /c 1234560 /n >nul
set "SEL=%errorlevel%"

if "!SEL!"=="7" goto MAIN
if "!SEL!"=="6" goto DO_STOP
if "!SEL!"=="5" goto CREATE_SHORTCUT
if "!SEL!"=="4" goto VPN_MENU
if "!SEL!"=="3" goto TOGGLE_LOGS
if "!SEL!"=="2" goto TOGGLE_HIDDEN
if "!SEL!"=="1" goto TOGGLE_AUTOSTART
goto SETTINGS_LOOP

:: ── Toggle autostart ──
:TOGGLE_AUTOSTART
if "!CFG_AUTOSTART!"=="1" (
    set "CFG_AUTOSTART=0"
    schtasks /delete /tn "sandusr" /f >nul 2>&1
    echo   Автозапуск: OFF
) else (
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
    echo     1. ПКМ по ярлыку -^> Свойства
    echo     2. Поле "Быстрый вызов" -^> нажми Ctrl+Alt+S
    echo     3. OK
    echo.
) else (
    echo   [ERROR] Не удалось создать ярлык.
)
pause
goto SETTINGS_LOOP

:: ═══════════════════════════════════════════════════════════════
::  VPN SETTINGS MENU
:: ═══════════════════════════════════════════════════════════════
:VPN_MENU
:VPN_LOOP
cls
title sandusr — VPN

:: VPN status labels
if "!VPN_ENABLED!"=="1" (set "S_VPN_EN=ON ") else (set "S_VPN_EN=OFF")
if "!VPN_AUTO!"=="1" (set "S_VPN_AUTO=ON ") else (set "S_VPN_AUTO=OFF")

:: Get protocol name
for /f "delims=" %%p in ('python vpn_manager.py get_proto 2^>nul') do set "VPN_PROTO=%%p"
if not defined VPN_PROTO set "VPN_PROTO=---"

:: Get running status
for /f "delims=" %%r in ('python vpn_manager.py is_running 2^>nul') do set "VPN_RUN=%%r"
if "!VPN_RUN!"=="1" (set "S_VPN_STATUS=CONNECTED") else (set "S_VPN_STATUS=off")

:: Truncate link for display
set "VPN_LINK_SHOW=---"
if exist "vpn_link.txt" (
    for /f "usebackq delims=" %%l in ("vpn_link.txt") do (
        set "VPN_LINK_FULL=%%l"
        set "VPN_LINK_SHOW=!VPN_LINK_FULL:~0,35!..."
    )
)

echo.
echo   ┌──── VPN ────────────────────────────┐
echo   │                                    │
echo   │  Статус: !S_VPN_STATUS!  [!VPN_PROTO!]    │
echo   │  Ссылка:  !VPN_LINK_SHOW!          │
echo   │                                    │
echo   │  [1] VPN          !S_VPN_EN!               │
echo   │  [2] Вставить ссылку                  │
echo   │  [3] SOCKS порт   !VPN_SOCKS_PORT!           │
echo   │  [4] HTTP порт    !VPN_HTTP_PORT!           │
echo   │  [5] Авто-подкл.  !S_VPN_AUTO!               │
echo   │                                    │
echo   │  [6] Подключить сейчас              │
echo   │  [7] Отключить                      │
echo   │  [8] Проверить                      │
echo   │                                    │
echo   │  [D] Скачать xray-core              │
echo   │  [S] Ярлык Ctrl+Alt+I              │
echo   │                                    │
echo   │  [0] Назад                          │
echo   └────────────────────────────────────┘
echo.
choice /c 123456780DS /n >nul
set "SEL=%errorlevel%"

if "!SEL!"=="11" goto VPN_SHORTCUT
if "!SEL!"=="10" goto VPN_DOWNLOAD
if "!SEL!"=="9" goto SETTINGS_LOOP
if "!SEL!"=="8" goto VPN_TEST
if "!SEL!"=="7" goto VPN_DISCONNECT
if "!SEL!"=="6" goto VPN_CONNECT
if "!SEL!"=="5" goto TOGGLE_VPN_AUTO
if "!SEL!"=="4" goto SET_HTTP_PORT
if "!SEL!"=="3" goto SET_SOCKS_PORT
if "!SEL!"=="2" goto VPN_PASTE_LINK
if "!SEL!"=="1" goto TOGGLE_VPN_ENABLED
goto VPN_LOOP

:: ── Toggle VPN enabled ──
:TOGGLE_VPN_ENABLED
if "!VPN_ENABLED!"=="1" (
    set "VPN_ENABLED=0"
    echo   VPN: OFF
) else (
    set "VPN_ENABLED=1"
    echo   VPN: ON
)
call :SAVE_CFG
timeout /t 1 >nul
goto VPN_LOOP

:: ── Toggle VPN auto-connect ──
:TOGGLE_VPN_AUTO
if "!VPN_AUTO!"=="1" (
    set "VPN_AUTO=0"
    echo   Авто-подключение: OFF
) else (
    set "VPN_AUTO=1"
    echo   Авто-подключение: ON
)
call :SAVE_CFG
timeout /t 1 >nul
goto VPN_LOOP

:: ── Set SOCKS port ──
:SET_SOCKS_PORT
echo.
set /p "NEW_PORT=  Новый SOCKS порт (текущий: !VPN_SOCKS_PORT!): "
if not "!NEW_PORT!"=="" (
    set "VPN_SOCKS_PORT=!NEW_PORT!"
    echo   SOCKS порт: !VPN_SOCKS_PORT!
    call :SAVE_CFG
)
timeout /t 1 >nul
goto VPN_LOOP

:: ── Set HTTP port ──
:SET_HTTP_PORT
echo.
set /p "NEW_PORT=  Новый HTTP порт (текущий: !VPN_HTTP_PORT!): "
if not "!NEW_PORT!"=="" (
    set "VPN_HTTP_PORT=!NEW_PORT!"
    echo   HTTP порт: !VPN_HTTP_PORT!
    call :SAVE_CFG
)
timeout /t 1 >nul
goto VPN_LOOP

:: ── Paste VPN link ──
:VPN_PASTE_LINK
cls
echo.
echo   Вставьте ссылку (vless://, vmess://, trojan://, ss://, hy2://)
echo   и нажмите Enter. Ctrl+C для отмены.
echo.
set /p "VPN_INPUT=  Ссылка: "
if not "!VPN_INPUT!"=="" (
    echo !VPN_INPUT!>"vpn_link_tmp.txt"
    python vpn_manager.py set_link_from_file vpn_link_tmp.txt
    del vpn_link_tmp.txt >nul 2>&1
)
echo.
pause
goto VPN_LOOP

:: ── Connect VPN ──
:VPN_CONNECT
echo.
echo   Подключаю VPN...
echo.
python vpn_manager.py connect
echo.
pause
goto VPN_LOOP

:: ── Disconnect VPN ──
:VPN_DISCONNECT
echo.
echo   Отключаю VPN...
echo.
python vpn_manager.py disconnect
echo.
pause
goto VPN_LOOP

:: ── Test VPN ──
:VPN_TEST
cls
echo.
echo   ── Проверка VPN ──
echo.
python vpn_manager.py test
echo.
pause
goto VPN_LOOP

:: ── Download xray-core ──
:VPN_DOWNLOAD
cls
echo.
echo   ── Скачивание xray-core ──
echo   Будет скачана последняя версия для Windows 64-bit.
echo.
echo   Продолжить? [Y/N]
choice /c YN /n >nul
if %errorlevel%==2 goto VPN_LOOP
echo.
python vpn_manager.py download
echo.
pause
goto VPN_LOOP

:: ── Create VPN shortcut (Ctrl+Alt+I) ──
:VPN_SHORTCUT
echo.
echo   Создаю ярлык для быстрого доступа к VPN (Ctrl+Alt+I)...
set "LNK=%USERPROFILE%\Desktop\sandusr VPN.lnk"
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s = $ws.CreateShortcut('%LNK%');" ^
    "$s.TargetPath = '%~dp0start.bat';" ^
    "$s.Arguments = '/vpn';" ^
    "$s.WorkingDirectory = '%~dp0%';" ^
    "$s.Description = 'sandusr VPN settings';" ^
    "$s.Save()"
if exist "!LNK!" (
    echo.
    echo   Ярлык создан: %LNK%
    echo.
    echo   Чтобы поставить Ctrl+Alt+I:
    echo     1. ПКМ по ярлыку -^> Свойства
    echo     2. Поле "Быстрый вызов" -^> нажми Ctrl+Alt+I
    echo     3. OK
    echo.
) else (
    echo   [ERROR] Не удалось создать ярлык.
)
pause
goto VPN_LOOP

:: ═══════════════════════════════════════════════════════════════
::  HELPERS
:: ═══════════════════════════════════════════════════════════════

:SAVE_CFG
(
    echo AUTOSTART=!CFG_AUTOSTART!
    echo HIDDEN=!CFG_HIDDEN!
    echo LOGS=!CFG_LOGS!
    echo VPN_ENABLED=!VPN_ENABLED!
    echo VPN_SOCKS_PORT=!VPN_SOCKS_PORT!
    echo VPN_HTTP_PORT=!VPN_HTTP_PORT!
    echo VPN_AUTO=!VPN_AUTO!
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