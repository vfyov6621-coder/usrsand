"""
sandusr — Telegram userbot v3.0
Entry point with web panel.
"""
import os
import sys
import asyncio
import logging
import threading
import traceback

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
from loader import load_all_scripts
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

    if Config.PROXY:
        logger.info(f"Using proxy: {Config.PROXY['scheme']}://{Config.PROXY['hostname']}:{Config.PROXY['port']}")
        add_log(f"Proxy: {Config.PROXY['scheme']}://{Config.PROXY['hostname']}:{Config.PROXY['port']}")

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
    client.add_handler(MessageHandler(mm_cmd, filters.command("mm", prefixes=".") & filters.me))
    client.add_handler(CallbackQueryHandler(mm_cb, filters.regex(r"^mm_")))

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
        logger.error(f"Bot error: {e}")
        add_log(f"Bot error: {e}", "ERROR")
    finally:
        set_bot_status("offline")
        add_log("Bot stopped")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    # Start web panel in background thread
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
