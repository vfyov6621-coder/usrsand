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
_pyro_client = None  # set by main.py after client is created

AUTOSTART_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "autostart.json")


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


def set_pyro_client(client):
    """Store reference to the Pyrofork Client so web API can manage scripts."""
    global _pyro_client
    _pyro_client = client


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
        {"cmd": "-лм з/в/п/и <id>", "desc": "Управление скриптами"},
        {"cmd": "-з с/г/сп/у/у <имя>", "desc": "Заметки"},
        {"cmd": "-з <имя>", "desc": "Быстрый вызов заметки"},
        {"cmd": "-погода <город>", "desc": "Текущая погода"},
        {"cmd": "-погода п <город>", "desc": "Прогноз на 7 дней"},
        {"cmd": "-пер [язык] <текст>", "desc": "Перевод текста"},
        {"cmd": "-ям се/ов/по/пр/ст/пл/лк/диз", "desc": "Яндекс Музыка"},
        {"cmd": "-ии <текст>", "desc": "AI ассистент (Ollama)"},
        {"cmd": "-ии вк/вык", "desc": "Режим диалога AI"},
        {"cmd": "-ии оч", "desc": "Очистить историю AI"},
        {"cmd": "-гч с/о/сп/у <имя>", "desc": "Голосовые сообщения"},
        {"cmd": "-ад бн/рб/ки/мт/рм/бл/рбл", "desc": "Админ: бан/кик/мут/блок"},
        {"cmd": "-пр гр/с/сп/уд/ис/со/ид/со", "desc": "Премиум эмоджи"},
    ]
    return jsonify(commands)


# ── Autostart config ──

def _read_autostart():
    """Read autostart config. Returns set of script names, or None if all should load."""
    if not os.path.exists(AUTOSTART_FILE):
        return None  # None = load all (default)
    try:
        with open(AUTOSTART_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        mode = data.get("mode", "all")
        if mode == "all":
            return None
        return set(data.get("scripts", []))
    except Exception:
        return None


def _write_autostart(autostart_set):
    """Write autostart config."""
    if autostart_set is None:
        data = {"mode": "all", "scripts": []}
    else:
        data = {"mode": "selected", "scripts": sorted(autostart_set)}
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@app.route("/api/autostart", methods=["GET"])
def api_autostart_get():
    """Get autostart configuration."""
    current = _read_autostart()
    if current is None:
        return jsonify({"mode": "all", "scripts": []})
    return jsonify({"mode": "selected", "scripts": sorted(current)})


@app.route("/api/autostart/<script_name>", methods=["POST"])
def api_autostart_toggle(script_name):
    """Toggle autostart for a specific script. Body: {"enabled": true/false}"""
    # Validate script exists
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
    if not os.path.isdir(os.path.join(scripts_dir, script_name)):
        return jsonify({"success": False, "error": "Script not found"}), 404

    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled", True)

    current = _read_autostart()
    if current is None:
        # switching from "all" mode to "selected" mode
        # when enabling: start with all currently available scripts
        available = []
        for name in sorted(os.listdir(scripts_dir)):
            if os.path.isdir(os.path.join(scripts_dir, name)) and not name.startswith("_"):
                if os.path.exists(os.path.join(scripts_dir, name, "main.py")):
                    available.append(name)
        current = set(available)

    if enabled:
        current.add(script_name)
    else:
        current.discard(script_name)

    # If all scripts are selected, switch back to "all" mode
    all_scripts = set()
    for name in sorted(os.listdir(scripts_dir)):
        if os.path.isdir(os.path.join(scripts_dir, name)) and not name.startswith("_"):
            if os.path.exists(os.path.join(scripts_dir, name, "main.py")):
                all_scripts.add(name)
    if current >= all_scripts:
        current = None  # all mode

    _write_autostart(current)
    result_mode = "all" if current is None else "selected"
    return jsonify({"success": True, "mode": result_mode, "script": script_name, "enabled": enabled})


# ── Script management API ──

@app.route("/api/scripts/load/<script_name>", methods=["POST"])
def api_script_load(script_name):
    """Load a script via web panel."""
    if _pyro_client is None:
        return jsonify({"success": False, "error": "Бот не подключён"}), 503

    from loader import load_script, get_loaded_names

    if script_name in get_loaded_names():
        return jsonify({"success": False, "error": "Скрипт уже загружен"})

    result = load_script(script_name, _pyro_client)
    if result["success"]:
        # Update web state
        _bot_state["scripts"] = get_loaded_names()
        add_log(f"[web] Loaded script: {script_name}")
        return jsonify(result)
    else:
        add_log(f"[web] Error loading {script_name}: {result['error']}", "ERROR")
        return jsonify(result), 400


@app.route("/api/scripts/unload/<script_name>", methods=["POST"])
def api_script_unload(script_name):
    """Unload a script via web panel."""
    from loader import unload_script, get_loaded_names

    result = unload_script(script_name)
    if result["success"]:
        _bot_state["scripts"] = get_loaded_names()
        add_log(f"[web] Unloaded script: {script_name}")
        return jsonify(result)
    else:
        add_log(f"[web] Error unloading {script_name}: {result['error']}", "ERROR")
        return jsonify(result), 400


@app.route("/api/scripts/reload/<script_name>", methods=["POST"])
def api_script_reload(script_name):
    """Reload a script via web panel."""
    if _pyro_client is None:
        return jsonify({"success": False, "error": "Бот не подключён"}), 503

    from loader import unload_script, load_script, get_loaded_names

    unload_script(script_name)
    result = load_script(script_name, _pyro_client)
    if result["success"]:
        _bot_state["scripts"] = get_loaded_names()
        add_log(f"[web] Reloaded script: {script_name}")
        return jsonify(result)
    else:
        add_log(f"[web] Error reloading {script_name}: {result['error']}", "ERROR")
        return jsonify(result), 400
