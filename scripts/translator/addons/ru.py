"""Translator addon: Russian (.прру)"""

def register(client):
    import asyncio
    from deep_translator import GoogleTranslator
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import cmd, safe_edit

    async def tra_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "Нет текста для перевода.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "Перевод...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="ru").translate(text)
            )
            await safe_edit(message, f"<b>Перевод (RU):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"Ошибка перевода: {e}")

    client.add_handler(MessageHandler(tra_handler, cmd("прру") & filters.reply))

def on_load():
    print("[translator/ru] Loaded. .прру")
