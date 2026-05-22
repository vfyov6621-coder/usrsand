#!/bin/bash
# sandusr v3.0 — запуск с логами

mkdir -p logs
LOGFILE="logs/sandusr_$(date +%Y-%m-%d_%H-%M).log"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║          sandusr v3.0               ║"
echo "  ║     Telegram Userbot                ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  [INFO] Log: $LOGFILE"
echo "  [INFO] Starting..."
echo ""

python3 main.py 2>&1 | tee "$LOGFILE"
