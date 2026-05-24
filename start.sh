#!/bin/bash
# sandusr v3.0 — запуск с логами
#
# Лог-файл: logs/log_DD_MM_HH-MM-SS.txt

mkdir -p logs
LOGFILE="logs/log_$(date +%d_%m_%H-%M-%S).txt"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║          sandusr v3.0               ║"
echo "  ║     Telegram Userbot                ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  [LOG] $LOGFILE"
echo ""

python3 main.py 2>&1 | tee "$LOGFILE"
