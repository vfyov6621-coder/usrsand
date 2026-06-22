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


# ═══════════════════════════════════════════════════════════════
#  AI Chat — Settings & History
# ═══════════════════════════════════════════════════════════════

AI_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scripts", "ai_chat", "settings.json",
)
AI_HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scripts", "ai_chat", "history",
)


def _ai_load_settings():
    try:
        if os.path.exists(AI_SETTINGS_FILE):
            with open(AI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "provider": "ollama",
        "api_base": "https://api.deepseek.com",
        "api_key": "",
        "model": "qwen2.5:1.5b",
        "system": "",
        "agent_chats": [],
    }


def _ai_save_settings(s):
    os.makedirs(os.path.dirname(AI_SETTINGS_FILE), exist_ok=True)
    with open(AI_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


@app.route("/api/ai/settings", methods=["GET"])
def api_ai_settings_get():
    """Get AI chat settings (key masked)."""
    s = _ai_load_settings()
    key = s.get("api_key", "")
    if key:
        s["api_key_masked"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    else:
        s["api_key_masked"] = ""
    # Don't send full key to frontend
    s["has_key"] = bool(key)
    s.pop("api_key", None)
    return jsonify(s)


@app.route("/api/ai/settings", methods=["POST"])
def api_ai_settings_post():
    """Update AI chat settings. Body: partial JSON with fields to update."""
    body = request.get_json(silent=True) or {}
    s = _ai_load_settings()

    if "provider" in body and body["provider"] in ("ollama", "api"):
        s["provider"] = body["provider"]
    if "api_base" in body:
        s["api_base"] = body["api_base"]
    if "api_key" in body:
        new_key = body["api_key"]
        if new_key and new_key != "__________":
            # If user typed a new key, save it
            s["api_key"] = new_key
        # If placeholder, keep existing key
    if "model" in body:
        s["model"] = body["model"]
    if "system" in body:
        s["system"] = body["system"]

    _ai_save_settings(s)
    add_log(f"[web] AI settings updated")

    # Return masked view
    key = s.get("api_key", "")
    return jsonify({
        "success": True,
        "provider": s.get("provider", "ollama"),
        "api_base": s.get("api_base", ""),
        "has_key": bool(key),
        "api_key_masked": key[:8] + "..." + key[-4:] if len(key) > 12 else ("***" if key else ""),
        "model": s.get("model", ""),
        "system": s.get("system", ""),
    })


@app.route("/api/ai/test", methods=["POST"])
def api_ai_test():
    """Test AI provider connection. Returns {ok, models}."""
    s = _ai_load_settings()
    provider = s.get("provider", "ollama")

    try:
        if provider == "api":
            import requests
            api_key = s.get("api_key", "")
            api_base = s.get("api_base", "https://api.deepseek.com").rstrip("/")
            headers = {"Authorization": f"Bearer {api_key}"}
            models_url = api_base + "/models" if api_base.endswith("/v1") else api_base + "/v1/models"
            r = requests.get(models_url, headers=headers, timeout=10)
            if r.status_code == 200:
                models = [m.get("id", "") for m in r.json().get("data", [])]
                return jsonify({"ok": True, "provider": "api", "models": sorted(models)[:20]})
            return jsonify({"ok": False, "provider": "api", "error": f"HTTP {r.status_code}"})
        else:
            import requests
            ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
            r = requests.get(f"{ollama_url}/api/tags", timeout=5)
            if r.status_code == 200:
                models = [m.get("name", "") for m in r.json().get("models", [])]
                return jsonify({"ok": True, "provider": "ollama", "models": models})
            return jsonify({"ok": False, "provider": "ollama", "error": f"HTTP {r.status_code}"})
    except Exception as e:
        return jsonify({"ok": False, "provider": provider, "error": str(e)[:200]})


@app.route("/api/ai/history", methods=["GET"])
def api_ai_history_list():
    """List all chat histories: [{chat_id, messages, size_bytes}]."""
    result = []
    if not os.path.isdir(AI_HISTORY_DIR):
        return jsonify(result)
    for fname in sorted(os.listdir(AI_HISTORY_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(AI_HISTORY_DIR, fname)
        chat_id = fname[:-5]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                msg_count = len(data)
            else:
                msg_count = 0
            size = os.path.getsize(fpath)
            result.append({
                "chat_id": chat_id,
                "messages": msg_count,
                "size_bytes": size,
            })
        except Exception:
            result.append({"chat_id": chat_id, "messages": 0, "size_bytes": 0})
    # Sort by chat_id
    result.sort(key=lambda x: x["chat_id"])
    return jsonify(result)


@app.route("/api/ai/history/<chat_id>", methods=["GET"])
def api_ai_history_get(chat_id):
    """Get full history for a chat."""
    fpath = os.path.join(AI_HISTORY_DIR, f"{chat_id}.json")
    if not os.path.exists(fpath):
        return jsonify({"error": "not found"}), 404
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"chat_id": chat_id, "history": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai/history/<chat_id>", methods=["DELETE"])
def api_ai_history_delete(chat_id):
    """Clear history for a chat."""
    fpath = os.path.join(AI_HISTORY_DIR, f"{chat_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)
        add_log(f"[web] AI history cleared: {chat_id}")
    return jsonify({"success": True})
