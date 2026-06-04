"""
sandusr — Telegram userbot v3.0
Entry point with web panel.
"""
import os
import sys
import socket
import asyncio
import logging
import threading
import traceback
import json
import importlib
import random
import math
import time

# ═══════════════════════════════════════════════════════════════════════
#  Connection fixes — MUST be before any imports that use network
# ═══════════════════════════════════════════════════════════════════════

# 1) Force IPv4 — VPNs on Windows often break IPv6 routing
_original_getaddrinfo = socket.getaddrinfo

def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Force IPv4 only — prevents IPv6 timeout through VPN."""
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

if os.environ.get("FORCE_IPV4", "1").lower() in ("1", "true", "yes"):
    socket.getaddrinfo = _ipv4_only_getaddrinfo

# 2) Windows event loop fix
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from pyrogram import Client, filters, idle
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from loader import load_all_scripts, load_script, unload_script, reload_script, get_script_info, get_loaded_names, get_available
from web import app, set_bot_status, set_loaded_scripts, add_log, set_pyro_client
from scripts._utils import cmd

# Simple logging — console + file
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)

log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=date_format,
)
logger = logging.getLogger("sandusr")

# Add file handler — logs/DEBUG.log (all levels)
_file_handler = logging.FileHandler(
    os.path.join(log_dir, "DEBUG.log"), mode="a", encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
logging.getLogger().addHandler(_file_handler)

VERSION = Config.VERSION
BOT_NAME = "sandusr"
_loaded_scripts = []
PHOTO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_photo.jpg")
MAX_CONNECT_ATTEMPTS = 5


# ═══════════════════════════════════════════════════════════════════════
#  Network diagnostics
# ═══════════════════════════════════════════════════════════════════════

def _check_network():
    """Pre-flight network check. Returns list of issues."""
    issues = []

    # Check python-socks if proxy configured
    if Config.PROXY:
        try:
            import socksio  # noqa: F401
            logger.info("python-socks (socksio): installed")
        except ImportError:
            try:
                import python_socks  # noqa: F401
                logger.info("python-socks: installed")
            except ImportError:
                issues.append(
                    "PROXY set in .env but python-socks NOT installed! "
                    "Proxy will be IGNORED. Run: pip install python-socks[asyncio]"
                )
                logger.warning("PROXY is set but python-socks NOT installed!")

    # Test DNS resolution
    for host in ["api.telegram.org", "149.154.167.50"]:
        try:
            socket.setdefaulttimeout(5)
            addr = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            if addr:
                logger.info(f"DNS OK: {host} -> {addr[0][4][0]}")
            else:
                issues.append(f"DNS failed for {host} (empty result)")
        except socket.gaierror:
            issues.append(f"DNS failed for {host} — cannot resolve hostname")
        except socket.timeout:
            issues.append(f"DNS timeout for {host} — network/firewall issue")
        except Exception as e:
            issues.append(f"DNS error for {host}: {e}")
        finally:
            socket.setdefaulttimeout(None)

    # Test TCP connection to Telegram DC
    for ip, port in [("149.154.167.50", 443), ("149.154.175.50", 443)]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ip, port))
            sock.close()
            logger.info(f"TCP OK: {ip}:{port}")
        except socket.timeout:
            issues.append(f"TCP timeout to {ip}:{port} — Telegram blocked or VPN not working")
        except ConnectionRefusedError:
            issues.append(f"TCP refused by {ip}:{port} — port blocked")
        except OSError as e:
            issues.append(f"TCP error to {ip}:{port}: {e}")
        except Exception as e:
            issues.append(f"TCP error to {ip}:{port}: {e}")

    # Check proxy TCP if configured
    if Config.PROXY:
        proxy_host = Config.PROXY.get("hostname", "?")
        proxy_port = Config.PROXY.get("port", "?")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((proxy_host, proxy_port))
            sock.close()
            logger.info(f"Proxy TCP OK: {proxy_host}:{proxy_port}")
        except Exception as e:
            issues.append(f"Proxy unreachable {proxy_host}:{proxy_port}: {e}")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  NTP time sync — fix "msg_id belongs to over 30 seconds in the future"
# ═══════════════════════════════════════════════════════════════════════

def _ntp_get_offset(host="pool.ntp.org", port=123, timeout=5):
    """Query NTP server, return offset in seconds (local - server)."""
    import struct

    NTP_EPOCH = 2208988800  # 1900-01-01 -> 1970-01-01 delta

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        # NTP request packet (48 bytes, mode=3 client, version=4)
        req = b"\x1b" + 47 * b"\x00"
        sock.sendto(req, (host, port))
        resp, _ = sock.recvfrom(1024)

        if len(resp) < 48:
            return None

        unpacked = struct.unpack("!12I", resp[:48])
        # Transmit timestamp is at bytes 40-47 (words 10-11)
        tx_sec = unpacked[10]
        tx_frac = unpacked[11]

        server_time = tx_sec - NTP_EPOCH + tx_frac / 2**32
        local_time = time.time()
        offset = local_time - server_time

        return offset
    except Exception as e:
        logger.debug("NTP query failed: %s", e)
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _sync_clock():
    """Check system clock via NTP, try to fix if offset > 10s.

    Returns True if time is OK or was fixed.
    """
    add_log("Checking system clock via NTP...")

    for host in ["pool.ntp.org", "time.windows.com", "time.google.com"]:
        offset = _ntp_get_offset(host)
        if offset is not None:
            break

    if offset is None:
        add_log("NTP check failed — cannot verify clock", "WARN")
        logger.warning("NTP check failed, skipping clock sync")
        return True  # can't verify, assume OK

    sign = "+" if offset >= 0 else ""
    add_log(f"Clock offset: {sign}{offset:.2f}s")

    if abs(offset) <= 10:
        logger.info("Clock OK (offset %.1fs)", offset)
        return True

    # Clock is off — try to fix
    logger.warning("Clock is off by %.1f seconds! Attempting to fix...", offset)
    add_log(f"Clock is off by {sign}{offset:.2f}s — fixing...", "WARN")

    fixed = False

    # 1) Try Windows time sync
    if sys.platform == "win32":
        try:
            import subprocess
            result = subprocess.run(
                ["w32tm", "/resync", "/force"],
                capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                # Re-check offset
                new_offset = _ntp_get_offset()
                if new_offset is not None and abs(new_offset) <= 10:
                    logger.info("Clock synced via w32tm (offset now %.1fs)", new_offset)
                    add_log("Clock synced via Windows time service")
                    fixed = True
                else:
                    add_log("w32tm ran but clock still off", "WARN")
        except Exception as e:
            add_log(f"w32tm failed: {e}", "WARN")

    # 2) Try Linux ntpdate/chrony
    elif sys.platform == "linux" or sys.platform == "darwin":
        for cmd in [["sudo", "ntpdate", "-u", "pool.ntp.org"],
                     ["chronyc", "makestep"],
                     ["timedatectl", "set-ntp", "true"]]:
            try:
                import subprocess
                subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                new_offset = _ntp_get_offset()
                if new_offset is not None and abs(new_offset) <= 10:
                    logger.info("Clock synced via %s", cmd[0])
                    add_log(f"Clock synced via {cmd[0]}")
                    fixed = True
                    break
            except Exception:
                pass

    if not fixed:
        add_log(
            f"AUTO-FIX FAILED. Clock is {sign}{offset:.2f}s off.\n"
            "MANUAL FIX:\n"
            "  Windows: Settings → Time → Sync now\n"
            "  Linux: sudo timedatectl set-ntp true\n"
            "  Or: sudo ntpdate pool.ntp.org",
            "ERROR",
        )

    return fixed


# ═══════════════════════════════════════════════════════════════════════
#  Patch Pyrogram/Pyrofork connection timeout
# ═══════════════════════════════════════════════════════════════════════

def _patch_pyrogram_timeout():
    """Brute-force patch ALL timeout constants in pyrogram connection modules."""
    patched = False
    timeout_val = 30

    targets = [
        ("pyrogram.connection.connection", ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT", "timeout"]),
        ("pyrogram.connection.tcp.tcp", ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT", "timeout"]),
        ("pyrogram.connection.tcp.abridged", ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT"]),
        ("pyrogram.connection.tcp.full", ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT"]),
        ("pyrogram.connection.tcp.intermediate", ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT"]),
        ("pyrogram.connection.tcp.obfuscated2", ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT"]),
    ]

    for mod_path, attrs in targets:
        try:
            mod = importlib.import_module(mod_path)
            for attr in attrs:
                if hasattr(mod, attr):
                    old_val = getattr(mod, attr)
                    if isinstance(old_val, (int, float)) and old_val < timeout_val:
                        setattr(mod, attr, timeout_val)
                        logger.info(f"Patched {mod_path}.{attr}: {old_val}s -> {timeout_val}s")
                        patched = True
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Patch {mod_path}: {e}")

    # Also try on Connection class directly
    try:
        from pyrogram.connection.connection import Connection
        for attr in ["CONNECTION_TIMEOUT", "CONNECT_TIMEOUT", "timeout"]:
            if hasattr(Connection, attr):
                old_val = getattr(Connection, attr)
                if isinstance(old_val, (int, float)) and old_val < timeout_val:
                    setattr(Connection, attr, timeout_val)
                    logger.info(f"Patched Connection.{attr}: {old_val}s -> {timeout_val}s")
                    patched = True
    except Exception:
        pass

    if not patched:
        logger.warning("Could not patch Pyrogram timeout — using default")


# ═══════════════════════════════════════════════════════════════════════
#  -меню — menu
# ═══════════════════════════════════════════════════════════════════════

MM_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏓 Пинг", callback_data="mm_ping")],
    [InlineKeyboardButton("ℹ️ Инфо", callback_data="mm_info")],
    [InlineKeyboardButton("👤 Владелец", callback_data="mm_owner")],
])


async def mm_cmd(client, message: Message):
    text = f"🤖 <b>{BOT_NAME}</b> v{VERSION}\n\nВыберите действие:"
    if os.path.exists(PHOTO_FILE):
        try:
            await message.edit_text(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)
        except Exception:
            try:
                await message.reply_photo(PHOTO_FILE, caption=text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)
            except Exception:
                await message.reply(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)
    else:
        try:
            await message.edit_text(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)


async def mm_cb(client, callback: CallbackQuery):
    d = callback.data
    if d == "mm_ping":
        import time
        t0 = time.time()
        m = await callback.message.edit_text("🏓 Пинг...")
        ms = int((time.time() - t0) * 1000)
        await m.edit_text(f"🏓 <b>Пинг: {ms}ms</b>", parse_mode=ParseMode.HTML)
    elif d == "mm_info":
        await callback.message.edit_text(
            f"🤖 <b>{BOT_NAME}</b> v{VERSION}\n"
            f"📝 Модулей загружено: <b>{len(_loaded_scripts)}</b>",
            parse_mode=ParseMode.HTML
        )
    elif d == "mm_owner":
        me = client.me
        await callback.message.edit_text(
            f"👤 <b>Владелец</b>\n\n"
            f"📌 Имя: <b>{me.first_name}</b>\n"
            f"📌 ID: <code>{me.id}</code>\n"
            + (f"📌 Username: @{me.username}\n" if me.username else ""),
            parse_mode=ParseMode.HTML
        )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════
#  -мф  —  set menu photo from reply
# ═══════════════════════════════════════════════════════════════════════

async def mf_cmd(client, message: Message):
    """Reply to a photo to set it as the bot menu photo."""
    if not message.reply_to_message:
        await safe_edit(message,
            "❌ Ответьте на сообщение с фото:\n<code>-мф</code> (ответ на фото)",
            parse_mode=ParseMode.HTML,
        )
        return

    reply = message.reply_to_message
    if not reply.photo and not reply.sticker:
        await safe_edit(message,
            "❌ В ответе должно быть фото или стикер",
            parse_mode=ParseMode.HTML,
        )
        return

    await safe_edit(message, "📸 Сохранение фото...", parse_mode=ParseMode.HTML)

    try:
        if reply.photo:
            file = await client.download_media(reply.photo.file_id, file_name=PHOTO_FILE)
        else:
            file = await client.download_media(reply.sticker.file_id, file_name=PHOTO_FILE)

        if file:
            await safe_edit(message,
                "✅ Фото установлено!\n\nТеперь <code>-меню</code> покажет это фото.",
                parse_mode=ParseMode.HTML,
            )
            add_log("Menu photo updated")
        else:
            await safe_edit(message, "❌ Не удалось скачать фото", parse_mode=ParseMode.HTML)
    except Exception as e:
        await safe_edit(message, f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════════════
#  -рн  —  randomizer (non-uniform distribution)
# ═══════════════════════════════════════════════════════════════════════

async def rn_cmd(client, message: Message):
    """Random number with different probabilities. Usage: -рн 1 10"""
    from pyrogram.enums import ParseMode

    parts = message.text.split()
    if len(parts) < 3:
        await safe_edit(message,
            "❌ Использование: <code>-рн от до</code>\n"
            "Пример: <code>-рн 1 10</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        lo = int(parts[1])
        hi = int(parts[2])
    except ValueError:
        await safe_edit(message, "❌ Укажи числа. Пример: <code>-рн 1 10</code>", parse_mode=ParseMode.HTML)
        return

    if lo > hi:
        lo, hi = hi, lo

    n = hi - lo + 1  # amount of numbers
    if n == 1:
        await safe_edit(message, f"🎲 {lo}", parse_mode=ParseMode.HTML)
        return

    # Generate non-uniform weights: each number gets a unique random weight
    # so every number has a different chance
    raw = [random.random() for _ in range(n)]
    # Normalize to probabilities
    total = sum(raw)
    weights = [w / total for w in raw]

    result = random.choices(range(lo, hi + 1), weights=weights, k=1)[0]

    # Build chance display (sorted by chance descending)
    indexed = sorted(enumerate(weights), key=lambda x: -x[1])
    chance_lines = []
    for idx, w in indexed[:10]:  # top 10 max
        num = lo + idx
        pct = w * 100
        chance_lines.append(f"  <b>{num}</b> — {pct:.1f}%")

    text = (
        f"🎲 Выпало: <b>{result}</b>\n\n"
        f"<i>Шансы ({lo}–{hi}):</i>\n"
        + "\n".join(chance_lines)
    )
    if n > 10:
        text += f"\n  ...и ещё {n - 10} чисел"
    await safe_edit(message, text, parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════════════
#  -лм  —  script management
# ═══════════════════════════════════════════════════════════════════════

async def lm_cmd(client, message: Message):
    """Handler for -лм command — script management."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await _lm_list(message)
        return

    action = args[1].strip()
    add_log(f"-лм {action} from {message.from_user.id}" if message.from_user else f"-лм {action}")

    if action == "list" or action == "список":
        await _lm_list(message)
    elif action.startswith("load ") or action.startswith("загрузить "):
        if action.startswith("загрузить "):
            sid = action[len("загрузить "):].strip()
        else:
            sid = action[5:].strip()
        await _lm_load(client, message, sid)
    elif action.startswith("unload ") or action.startswith("выгрузить "):
        if action.startswith("выгрузить "):
            sid = action[len("выгрузить "):].strip()
        else:
            sid = action[7:].strip()
        await _lm_unload(message, sid)
    elif action.startswith("reload ") or action.startswith("перезагрузить "):
        if action.startswith("перезагрузить "):
            sid = action[len("перезагрузить "):].strip()
        else:
            sid = action[7:].strip()
        await _lm_reload(client, message, sid)
    elif action.startswith("info ") or action.startswith("инфо "):
        if action.startswith("инфо "):
            sid = action[len("инфо "):].strip()
        else:
            sid = action[5:].strip()
        await _lm_info(message, sid)
    else:
        await safe_edit(message, f"Неизвестная команда: <code>{action}</code>", parse_mode=ParseMode.HTML)


def _read_meta(script_id):
    """Read meta.json for a script, return dict or None."""
    try:
        path = os.path.join(Config.SCRIPTS_DIR, script_id, "meta.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


async def _lm_list(message: Message):
    available = get_available()
    loaded = get_loaded_names()

    text = "<b>Скрипты:</b>\n\n"
    text += "<b>Загружены:</b>\n"
    if loaded:
        for sid in loaded:
            meta = _read_meta(sid)
            cmd_str = meta.get("command", "") if meta else ""
            if cmd_str:
                text += f"  ✅ <code>{sid}</code> — <code>{cmd_str}</code>\n"
            else:
                text += f"  ✅ <code>{sid}</code>\n"
    else:
        text += "  <i>Нет</i>\n"

    not_loaded = [s for s in available if s not in loaded]
    text += "\n<b>Доступны:</b>\n"
    if not_loaded:
        for sid in not_loaded:
            meta = _read_meta(sid)
            cmd_str = meta.get("command", "") if meta else ""
            if cmd_str:
                text += f"  ⬜ <code>{sid}</code> — <code>{cmd_str}</code>\n"
            else:
                text += f"  ⬜ <code>{sid}</code>\n"
    else:
        text += "  <i>Все загружены</i>\n"

    text += f"\nВсего: {len(available)}"
    await safe_edit(message, text, parse_mode=ParseMode.HTML)


async def _lm_load(client, message: Message, script_id: str):
    result = load_script(script_id, client)
    if result["success"]:
        addons = result.get("addons", [])
        text = f"✅ Скрипт <code>{script_id}</code> загружен!"
        if addons:
            text += f"\n🔌 Аддоны: {', '.join(addons)}"
        await safe_edit(message, text, parse_mode=ParseMode.HTML)
        add_log(f"Script {script_id} loaded")
        _loaded_scripts.append(script_id)
        set_loaded_scripts(_loaded_scripts)
    else:
        await safe_edit(message, f"❌ Ошибка: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)
        add_log(f"Error loading {script_id}: {result['error']}", "ERROR")


async def _lm_unload(message: Message, script_id: str):
    result = unload_script(script_id)
    if result["success"]:
        await safe_edit(message, f"✅ Скрипт <code>{script_id}</code> выгружен", parse_mode=ParseMode.HTML)
        add_log(f"Script {script_id} unloaded")
        if script_id in _loaded_scripts:
            _loaded_scripts.remove(script_id)
            set_loaded_scripts(_loaded_scripts)
    else:
        await safe_edit(message, f"❌ Ошибка: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)


async def _lm_reload(client, message: Message, script_id: str):
    unload_script(script_id)
    result = load_script(script_id, client)
    if result["success"]:
        addons = result.get("addons", [])
        text = f"✅ Скрипт <code>{script_id}</code> перезагружен!"
        if addons:
            text += f"\n🔌 Аддоны: {', '.join(addons)}"
        await safe_edit(message, text, parse_mode=ParseMode.HTML)
        add_log(f"Script {script_id} reloaded")
        if script_id not in _loaded_scripts:
            _loaded_scripts.append(script_id)
        set_loaded_scripts(_loaded_scripts)
    else:
        await safe_edit(message, f"❌ Ошибка: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)
        add_log(f"Error reloading {script_id}: {result['error']}", "ERROR")


async def _lm_info(message: Message, script_id: str):
    info = get_script_info(script_id)
    if info is None:
        await safe_edit(message, f"❌ Скрипт <code>{script_id}</code> не найден", parse_mode=ParseMode.HTML)
        return

    text = (
        f"<b>{info['name']}</b>\n\n"
        f"ID: <code>{info['id']}</code>\n"
        f"Загружен: {'✅ Да' if info['loaded'] else '❌ Нет'}\n"
        f"Размер: {info.get('size', '?')} байт\n"
        f"Строк: {info.get('lines', '?')}\n"
    )
    if info.get("modified"):
        text += f"Изменён: {info['modified']}\n"
    if info.get("description"):
        text += f"\nОписание: <i>{info['description']}</i>\n"
    if info.get("addons"):
        text += f"\n<b>Аддоны:</b>\n"
        for addon in info["addons"]:
            text += f"  📎 {addon}\n"

    # Read meta.json for commands
    meta = _read_meta(script_id)
    if meta and meta.get("commands"):
        text += "\n<b>Команды:</b>\n"
        for c in meta["commands"]:
            text += f"  ⚡ <code>{c}</code>\n"

    await safe_edit(message, text, parse_mode=ParseMode.HTML)


async def safe_edit(message, text, **kwargs):
    """Safe edit with fallback to reply."""
    try:
        return await message.edit_text(text, **kwargs)
    except Exception:
        try:
            return await message.reply(text, quote=False, **kwargs)
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════
#  Web panel (Flask in separate thread)
# ═══════════════════════════════════════════════════════════════════════

def _start_web_panel(port):
    """Run Flask in a daemon thread."""
    try:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Web panel error: {e}")


# ═══════════════════════════════════════════════════════════════════════
#  Bot startup
# ═══════════════════════════════════════════════════════════════════════

async def main():
    global _loaded_scripts

    if not Config.API_ID or not Config.API_HASH:
        logger.error("API_ID and API_HASH not configured!")
        add_log("ERROR: API_ID and API_HASH not configured!", "ERROR")
        return

    # Patch timeout
    _patch_pyrogram_timeout()

    # Proxy check
    if Config.PROXY:
        p = Config.PROXY
        logger.info(f"Using proxy: {p['scheme']}://{p['hostname']}:{p['port']}")
        add_log(f"Proxy: {p['scheme']}://{p['hostname']}:{p['port']}")
        # Verify python-socks is installed
        try:
            import socksio  # noqa: F401
        except ImportError:
            try:
                import python_socks  # noqa: F401
            except ImportError:
                logger.error(
                    "PROXY is set but python-socks NOT installed!\n"
                    "Proxy will be IGNORED by Pyrogram.\n"
                    "Run: pip install python-socks[asyncio]"
                )
                add_log("ERROR: proxy set but python-socks not installed!", "ERROR")
                add_log("FIX: pip install python-socks[asyncio]", "ERROR")
                return
    else:
        logger.info("No proxy configured. If Telegram is blocked, set PROXY in .env")

    # Build client
    client = Client(
        name="userbot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE or None,
        session_string=Config.SESSION_STRING or None,
        workdir=Config.BASE_DIR,
        proxy=Config.PROXY or None,
    )

    # Register built-in commands
    client.add_handler(MessageHandler(rn_cmd, cmd("рн")))
    client.add_handler(MessageHandler(mm_cmd, cmd("меню")))
    client.add_handler(CallbackQueryHandler(mm_cb, filters.regex(r"^mm_")))
    client.add_handler(MessageHandler(mf_cmd, cmd("мф") & filters.reply))
    client.add_handler(MessageHandler(lm_cmd, cmd("лм")))

    # Load all scripts
    _loaded_scripts = load_all_scripts(client)
    set_loaded_scripts(_loaded_scripts)
    set_pyro_client(client)
    add_log(f"Loaded {len(_loaded_scripts)} scripts: {', '.join(_loaded_scripts)}")
    logger.info(f"Loaded {len(_loaded_scripts)} scripts: {', '.join(_loaded_scripts)}")

    # ═══ Connect with retry limit ═══
    attempt = 0
    while attempt < MAX_CONNECT_ATTEMPTS:
        attempt += 1
        logger.info(f"Connection attempt {attempt}/{MAX_CONNECT_ATTEMPTS}...")
        add_log(f"Connect attempt {attempt}/{MAX_CONNECT_ATTEMPTS}")
        try:
            async with client:
                me = await client.get_me()
                account = f"@{me.username}" if me.username else me.first_name
                set_bot_status("online", account)
                add_log(f"Started as {account} (ID: {me.id})")
                logger.info(f"Started as {account} (ID: {me.id})")
                await idle()
                return
        except Exception as e:
            err_str = str(e)
            logger.error(f"Attempt {attempt} failed: {err_str}")
            add_log(f"Connect attempt {attempt} failed: {err_str[:100]}", "ERROR")

            if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                if attempt < MAX_CONNECT_ATTEMPTS:
                    logger.info(f"Timeout. Retrying in 5s... ({attempt}/{MAX_CONNECT_ATTEMPTS})")
                    add_log(f"Timeout, retrying in 5s ({attempt}/{MAX_CONNECT_ATTEMPTS})")
                    await asyncio.sleep(5)
                    continue

            # Non-timeout error — don't retry
            if "api id" in err_str.lower() or "api_hash" in err_str.lower():
                add_log("FIX: Check API_ID and API_HASH in .env", "ERROR")
                return
            if "flood" in err_str.lower():
                add_log("FIX: Flood wait. Try again later.", "ERROR")
                return
            if "auth" in err_str.lower() or "phone" in err_str.lower() or "session" in err_str.lower():
                add_log(f"Auth error: {err_str[:200]}", "ERROR")
                return

            # Unknown error — retry if attempts left
            if attempt < MAX_CONNECT_ATTEMPTS:
                logger.info(f"Retrying in 5s... ({attempt}/{MAX_CONNECT_ATTEMPTS})")
                await asyncio.sleep(5)
                continue

    # All attempts failed
    set_bot_status("offline")
    add_log("Bot stopped — connection failed", "ERROR")
    logger.error(
        f"\n{'='*50}\n"
        f"FAILED after {MAX_CONNECT_ATTEMPTS} attempts.\n"
        f"{'='*50}\n\n"
        f"Your VPN is NOT routing to Telegram.\n\n"
        f"Fix options:\n\n"
        f"  1) PROXY in .env (recommended):\n"
        f"     PROXY=socks5://user:pass@host:port\n"
        f"     pip install python-socks[asyncio]\n\n"
        f"  2) Use a VPN that works with Telegram\n"
        f"     (test: can you open web.telegram.org in browser?)\n\n"
        f"  3) Free SOCKS5 (temporary):\n"
        f"     PROXY=socks5://host:port\n"
        f"     https://hidemy.name/en/proxy-list/\n"
        f"{'='*50}"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    # ── Pre-flight network check ──
    logger.info("Running network diagnostics...")
    add_log("Network diagnostics...")
    issues = _check_network()

    if issues:
        for issue in issues:
            logger.warning(f"Network issue: {issue}")
            add_log(f"Network issue: {issue}", "WARN")
        logger.warning(
            "Network issues detected! Check warnings above.\n"
            "If Telegram is blocked, set PROXY=socks5://host:port in .env\n"
            "And run: pip install python-socks[asyncio]"
        )
    else:
        logger.info("Network diagnostics: all OK")
        add_log("Network: all OK")

    # ── Clock sync check (fixes msg_id 30s error) ──
    clock_ok = _sync_clock()
    if not clock_ok:
        logger.error(
            "System clock is out of sync! Telegram requires ±30s accuracy.\n"
            "Fix manually:\n"
            "  Windows: Settings → Time & Language → Sync now\n"
            "  Linux: sudo timedatectl set-ntp true"
        )
        # Don't exit — let Pyrofork try anyway, user can see the error

    # ── Start ──
    web_thread = threading.Thread(target=_start_web_panel, args=(port,), daemon=True)
    web_thread.start()
    logger.info(f"Web panel: http://localhost:{port}")
    add_log(f"Web panel started on port {port}")
    logger.info("Starting userbot...")
    add_log("Starting userbot...")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.critical(f"Fatal: {e}")
        logger.critical(traceback.format_exc())
