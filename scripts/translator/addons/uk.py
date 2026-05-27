"""Translator addon: Українська (.tru)"""

def register(client):
    import asyncio
    from deep_translator import GoogleTranslator
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import cmd, safe_edit

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

    client.add_handler(MessageHandler(tru_handler, cmd("tru") & filters.reply))

def on_load():
    print("[translator/uk] Loaded. .tru")
