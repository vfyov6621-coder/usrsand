"""Translator addon: Francais (.trf)"""

def register(client):
    import asyncio
    from deep_translator import GoogleTranslator
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    async def trf_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.text or reply.caption):
            await safe_edit(message, "Pas de texte.")
            return
        text = reply.text or reply.caption
        await safe_edit(message, "Traduction...")
        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None, lambda: GoogleTranslator(source="auto", target="fr").translate(text)
            )
            await safe_edit(message, f"<b>Traduction (FR):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"Erreur: {e}")

    client.add_handler(MessageHandler(trf_handler, filters.command("trf", prefixes=".") & filters.reply & filters.me))

def on_load():
    print("[translator/fr] Loaded. .trf")
