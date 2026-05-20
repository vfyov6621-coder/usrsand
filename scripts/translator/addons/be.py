"""Translator addon: Беларуская (.trb)"""
import asyncio
from deep_translator import GoogleTranslator
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from scripts._utils import safe_edit

def register(client):
    @client.on_message(filters.command("trb", prefixes=".") & filters.reply & filters.me)
    async def trb_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "Няма тэксту.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "Пераклад...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="be").translate(text)
            )
            await safe_edit(message, f"<b>Пераклад (BE):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"Памылка: {e}")

def on_load():
    print("[translator/be] Loaded. .trb")
