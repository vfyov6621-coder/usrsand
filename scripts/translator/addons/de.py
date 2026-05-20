"""Translator addon: Deutsch (.trd)"""

def register(client):
    import asyncio
    from deep_translator import GoogleTranslator
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    @client.on_message(filters.command("trd", prefixes=".") & filters.reply & filters.me)
    async def trd_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "No text to translate.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "Ubersetzung...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="de").translate(text)
            )
            await safe_edit(message, f"<b>Ubersetzung (DE):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"Fehler: {e}")

def on_load():
    print("[translator/de] Loaded. .trd")
