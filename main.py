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
from web import app, set_bot_status, set_loaded_scripts, add_log

# Simple logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sandusr")

VERSION = Config.VERSION
BOT_NAME = "sandusr"
_loaded_scripts = []
PHOTO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_photo.jpg")


# ═══════════════════════════════════════════════════════════════════════
#  Network diagnostics
# ═══════════════════════════════════════════════════════════════════════

def _check_network():
    """Pre-flight network check. Returns list of issues."""
    issues = []

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
            sock.settimeout(10)
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

    # Check proxy if configured
    if Config.PROXY:
        proxy_host = Config.PROXY.get("hostname", "?")
        proxy_port = Config.PROXY.get("port", "?")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((proxy_host, proxy_port))
            sock.close()
            logger.info(f"Proxy OK: {proxy_host}:{proxy_port}")
        except Exception as e:
            issues.append(f"Proxy unreachable {proxy_host}:{proxy_port}: {e}")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Patch Pyrogram connection timeout
# ═══════════════════════════════════════════════════════════════════════

def _patch_pyrogram_timeout():
    """Increase Pyrogram's default connection timeout from 10s to 30s."""
    try:
        from pyrogram.connection.connection import Connection
        Connection.CONNECTION_TIMEOUT = 30
        logger.info("Pyrogram connection timeout patched: 10s -> 30s")
    except Exception:
        try:
            # Pyrofork may have different structure
            import pyrogram.connection.tcp.tcp
            pyrogram.connection.tcp.tcp.Connection.CONNECT_TIMEOUT = 30
            logger.info("Pyrofork TCP connect timeout patched: 30s")
        except Exception:
            logger.debug("Could not patch Pyrogram timeout (not critical)")


# ═══════════════════════════════════════════════════════════════════════
#  .mm — menu
# ═══════════════════════════════════════════════════════════════════════

MM_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏓 Пинг", callback_data="mm_ping")],
    [InlineKeyboardButton("ℹ️ Инфо", callback_data="mm_info")],
    [InlineKeyboardButton("👤 Владелец", callback_data="mm_owner")],
])


async def mm_cmd(client, message: Message):
    text = f"🤖 <b>{BOT_NAME}</b> v{VERSION}\n\nВыберите действие:"
    # Try with photo if exists
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
#  .mf  —  set menu photo from reply
# ═══════════════════════════════════════════════════════════════════════

async def mf_cmd(client, message: Message):
    """Reply to a photo to set it as the bot menu photo."""
    if not message.reply_to_message:
        await safe_edit(message,
            "❌ Ответьте на сообщение с фото:\n<code>.mf</code> (ответ на фото)",
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
                "✅ Фото установлено!\n\nТеперь <code>.mm</code> покажет это фото.",
                parse_mode=ParseMode.HTML,
            )
            add_log("Menu photo updated")
        else:
            await safe_edit(message, "❌ Не удалось скачать фото", parse_mode=ParseMode.HTML)
    except Exception as e:
        await safe_edit(message, f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════════════
#  .lm  —  script management
# ═══════════════════════════════════════════════════════════════════════

async def lm_cmd(client, message: Message):
    """Handler for .lm command — script management."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await safe_edit(message,
            "<b>Управление скриптами:</b>\n\n"
            "  <code>.lm load &lt;id&gt;</code> — загрузить скрипт\n"
            "  <code>.lm unload &lt;id&gt;</code> — выгрузить\n"
            "  <code>.lm reload &lt;id&gt;</code> — перезагрузить\n"
            "  <code>.lm list</code> — список скриптов\n"
            "  <code>.lm info &lt;id&gt;</code> — инфо о скрипте",
            parse_mode=ParseMode.HTML,
        )
        return

    action = args[1].strip()
    add_log(f".lm {action} from {message.from_user.id}" if message.from_user else f".lm {action}")

    if action == "list":
        await _lm_list(message)
    elif action.startswith("load "):
        sid = action[5:].strip()
        await _lm_load(client, message, sid)
    elif action.startswith("unload "):
        sid = action[7:].strip()
        await _lm_unload(message, sid)
    elif action.startswith("reload "):
        sid = action[7:].strip()
        await _lm_reload(client, message, sid)
    elif action.startswith("info "):
        sid = action[5:].strip()
        await _lm_info(message, sid)
    else:
        await safe_edit(message, f"Неизвестная команда: <code>{action}</code>", parse_mode=ParseMode.HTML)


async def _lm_list(message: Message):
    """Show list of scripts (loaded + available)."""
    available = get_available()
    loaded = get_loaded_names()

    text = "<b>Скрипты:</b>\n\n"
    text += "<b>Загружены:</b>\n"
    if loaded:
        for sid in loaded:
            text += f"  ✅ <code>{sid}</code>\n"
    else:
        text += "  <i>Нет</i>\n"

    not_loaded = [s for s in available if s not in loaded]
    text += "\n<b>Доступны:</b>\n"
    if not_loaded:
        for sid in not_loaded:
            text += f"  ⬜ <code>{sid}</code>\n"
    else:
        text += "  <i>Все загружены</i>\n"

    text += f"\nВсего: {len(available)}"
    await safe_edit(message, text, parse_mode=ParseMode.HTML)


async def _lm_load(client, message: Message, script_id: str):
    """Load a script."""
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
    """Unload a script."""
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
    """Reload a script (unload + load)."""
    unload_script(script_id)  # ignore errors (may not be loaded)
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
    """Show info about a script."""
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

    # Proxy info
    if Config.PROXY:
        p = Config.PROXY
        logger.info(f"Using proxy: {p['scheme']}://{p['hostname']}:{p['port']}")
        add_log(f"Proxy: {p['scheme']}://{p['hostname']}:{p['port']}")

    # Build client kwargs
    client_kwargs = {
        "name": "userbot_session",
        "api_id": Config.API_ID,
        "api_hash": Config.API_HASH,
        "phone_number": Config.PHONE or None,
        "session_string": Config.SESSION_STRING or None,
        "workdir": Config.BASE_DIR,
        "proxy": Config.PROXY or None,
    }

    client = Client(**client_kwargs)

    # Register built-in commands
    client.add_handler(MessageHandler(mm_cmd, filters.command("mm", prefixes=".") & filters.me))
    client.add_handler(CallbackQueryHandler(mm_cb, filters.regex(r"^mm_")))
    client.add_handler(MessageHandler(mf_cmd, filters.command("mf", prefixes=".") & filters.me & filters.reply))
    client.add_handler(MessageHandler(lm_cmd, filters.command("lm", prefixes=".") & filters.me))

    # Load all scripts
    _loaded_scripts = load_all_scripts(client)
    set_loaded_scripts(_loaded_scripts)
    add_log(f"Loaded {len(_loaded_scripts)} scripts: {', '.join(_loaded_scripts)}")
    logger.info(f"Loaded {len(_loaded_scripts)} scripts: {', '.join(_loaded_scripts)}")

    try:
        async with client:
            me = await client.get_me()
            account = f"@{me.username}" if me.username else me.first_name
            set_bot_status("online", account)
            add_log(f"Started as {account} (ID: {me.id})")
            logger.info(f"Started as {account} (ID: {me.id})")
            await idle()
    except Exception as e:
        err_str = str(e)
        logger.error(f"Bot error: {err_str}")
        add_log(f"Bot error: {err_str}", "ERROR")

        # Helpful error messages
        if "timed out" in err_str.lower() or "timeout" in err_str.lower():
            tip = (
                "CONNECTION TIP: Telegram is unreachable!\n"
                "Options:\n"
                "  1) Use a VPN that works with Telegram\n"
                "  2) Set PROXY in .env: PROXY=socks5://host:port\n"
                "  3) pip install python-socks[asyncio] (for SOCKS5 proxy)\n"
                "  4) Set FORCE_IPV4=0 in .env if you need IPv6"
            )
            logger.error(tip)
            add_log(tip, "ERROR")
        elif "api id" in err_str.lower() or "api_hash" in err_str.lower():
            add_log("FIX: Check API_ID and API_HASH in .env", "ERROR")
    finally:
        set_bot_status("offline")
        add_log("Bot stopped")


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
            "Network issues detected! Telegram may not connect.\n"
            "Fix: use VPN or set PROXY=socks5://host:port in .env"
        )
    else:
        logger.info("Network diagnostics: all OK")
        add_log("Network: all OK")

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
