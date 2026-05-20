"""Translator addon: Українська (.tru)"""
import asyncio
from deep_translator import GoogleTranslator
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from scripts._utils import safe_edit

def register(client):
    @client.on_message(filters.command("tru", prefixes=".") & filters.reply & filters.me)
    async def tru_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "Немає тексту.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "Переклад...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="uk").translate(text)
            )
            await safe_edit(message, f"<b>Переклад (UK):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"Помилка: {e}")

def on_load():
    print("[translator/uk] Loaded. .tru")
