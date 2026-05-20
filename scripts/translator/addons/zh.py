"""Translator addon: Chinese (.trz)"""

def register(client):
    import asyncio
    from deep_translator import GoogleTranslator
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    async def trz_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "No text.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "翻译中...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="zh-cn").translate(text)
            )
            await safe_edit(message, f"<b>翻译 (ZH):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"错误: {e}")

    client.add_handler(MessageHandler(trz_handler, filters.command("trz", prefixes=".") & filters.reply & filters.me))

def on_load():
    print("[translator/zh] Loaded. .trz")
