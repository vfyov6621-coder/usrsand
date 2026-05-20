"""Translator addon: Chinese (.trz)"""
import asyncio
from deep_translator import GoogleTranslator
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from scripts._utils import safe_edit

def register(client):
    @client.on_message(filters.command("trz", prefixes=".") & filters.reply & filters.me)
    async def trz_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "No text.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "\u7ffb\u8bd1\u4e2d...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="zh-cn").translate(text)
            )
            await safe_edit(message, f"<b>\u7ffb\u8bd1 (ZH):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"\u9519\u8bef: {e}")

def on_load():
    print("[translator/zh] Loaded. .trz")
