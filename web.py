"""
sandusr — Web Panel
Flask-based dashboard for the userbot.
"""
import os
import json
import time
import logging
from datetime import datetime

from flask import Flask, render_template, jsonify, request

logger = logging.getLogger("sandusr.web")

# ── State shared with main.py ──
_bot_state = {
    "status": "offline",
    "started_at": None,
    "account": None,
    "scripts": [],
    "version": "3.0",
}

_log_buffer = []
_MAX_LOG_LINES = 200


def set_bot_status(status, account=None):
    _bot_state["status"] = status
    if account:
        _bot_state["account"] = account
    if status == "online" and not _bot_state["started_at"]:
        _bot_state["started_at"] = datetime.now().isoformat()
    elif status == "offline":
        _bot_state["started_at"] = None


def set_loaded_scripts(scripts):
    _bot_state["scripts"] = scripts


def add_log(message, level="INFO"):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message}
    _log_buffer.append(entry)
    if len(_log_buffer) > _MAX_LOG_LINES:
        _log_buffer.pop(0)


# ── Flask app ──
app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    uptime = None
    if _bot_state["started_at"]:
        try:
            started = datetime.fromisoformat(_bot_state["started_at"])
            uptime = int((datetime.now() - started).total_seconds())
        except Exception:
            pass

    return jsonify({
        "status": _bot_state["status"],
        "account": _bot_state["account"],
        "uptime": uptime,
        "version": _bot_state["version"],
        "scripts": _bot_state["scripts"],
        "scripts_count": len(_bot_state["scripts"]),
    })


@app.route("/api/logs")
def api_logs():
    return jsonify(_log_buffer[-100:])


@app.route("/api/scripts")
def api_scripts():
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
    result = []
    if not os.path.isdir(scripts_dir):
        return jsonify(result)

    for name in sorted(os.listdir(scripts_dir)):
        script_dir = os.path.join(scripts_dir, name)
        if not os.path.isdir(script_dir) or name.startswith("_"):
            continue

        meta_file = os.path.join(script_dir, "meta.json")
        meta = {}
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass

        main_file = os.path.join(script_dir, "main.py")
        lines = 0
        if os.path.exists(main_file):
            try:
                with open(main_file, "r", encoding="utf-8") as f:
                    lines = sum(1 for _ in f)
            except Exception:
                pass

        addons = []
        addons_dir = os.path.join(script_dir, "addons")
        if os.path.isdir(addons_dir):
            for af in sorted(os.listdir(addons_dir)):
                if af.endswith(".py"):
                    addons.append(af[:-3])

        is_loaded = name in _bot_state["scripts"]

        result.append({
            "id": name,
            "name": meta.get("name", name),
            "version": meta.get("version", "?"),
            "author": meta.get("author", "?"),
            "description": meta.get("description", ""),
            "command": meta.get("command", ""),
            "loaded": is_loaded,
            "lines": lines,
            "addons": addons,
        })

    return jsonify(result)


@app.route("/api/commands")
def api_commands():
    """List all available commands."""
    commands = [
        {"cmd": ".mm", "desc": "Меню бота"},
        {"cmd": ".ping", "desc": "Пинг юзербота"},
        {"cmd": ".note save/get/list/del/set", "desc": "Заметки"},
        {"cmd": ".n <name>", "desc": "Быстрый вызов заметки"},
        {"cmd": ".wea <city>", "desc": "Погода"},
        {"cmd": ".tr [lang] <text>", "desc": "Перевод текста"},
        {"cmd": ".tra/.trd/.trz/.trf/.tru/.trb", "desc": "Перевод (reply)"},
        {"cmd": ".ai <text>", "desc": "AI ассистент (Ollama)"},
        {"cmd": ".ai on/off", "desc": "Режим диалога"},
        {"cmd": ".ai clear", "desc": "Очистить историю AI"},
        {"cmd": ".ai model <name>", "desc": "Сменить модель AI"},
        {"cmd": ".ai status", "desc": "Статус Ollama"},
    ]
    return jsonify(commands)
