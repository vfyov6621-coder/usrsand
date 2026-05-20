"""
sandusr — Telegram userbot
Entry point. No web panel, no Flask — just the bot.
"""
import os
import sys
import asyncio
import logging
import traceback

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from loader import load_all_scripts

# Simple logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sandusr")

VERSION = Config.VERSION
BOT_NAME = "sandusr"

# ── .mm command ──
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

async def main():
    if not Config.API_ID or not Config.API_HASH:
        logger.error("API_ID and API_HASH not configured!")
        return

    client = Client(
        name="userbot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE or None,
        session_string=Config.SESSION_STRING or None,
        workdir=Config.BASE_DIR,
    )

    # Register built-in commands
    client.add_handler(MessageHandler(mm_cmd, filters.command("mm", prefixes=".") & filters.me))
    client.add_handler(CallbackQueryHandler(mm_cb, filters.regex(r"^mm_")))

    # Load all scripts
    global _loaded_scripts
    _loaded_scripts = load_all_scripts(client)

    logger.info(f"Loaded {len(_loaded_scripts)} scripts: {', '.join(_loaded_scripts)}")

    async with client:
        me = await client.get_me()
        logger.info(f"Started as @{me.username or me.first_name} (ID: {me.id})")
        await idle()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
