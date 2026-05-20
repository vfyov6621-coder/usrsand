"""Translator — .tr [lang] <text> or reply"""


def register(client):
    import asyncio
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.translator")

    async def tr_handler(client, message: Message):
        try:
            from deep_translator import GoogleTranslator

            args = message.text.split(maxsplit=1)

            if len(args) < 2:
                text = None
                lang = "en"
            else:
                potential_lang = args[1].split()[0] if args[1] else ""
                if len(potential_lang) == 2 and potential_lang.isalpha():
                    lang = potential_lang
                    try:
                        text = args[1].split(maxsplit=1)[1]
                    except IndexError:
                        text = None
                else:
                    text = args[1]
                    lang = "en"

            if not text:
                if message.reply_to_message:
                    text = message.reply_to_message.text
                    if not text:
                        await safe_edit(message, "Нет текста для перевода")
                        return
                else:
                    await safe_edit(message,
                        "Используйте: <code>.tr [lang] &lt;текст&gt;</code>\n"
                        "Или ответьте на сообщение командой <code>.tr [lang]</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return

            await safe_edit(message, "Перевод...")

            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target=lang).translate(text)
            )
            await safe_edit(message, f"<b>Перевод ({lang}):</b>\n\n<code>{translated}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"translate error: {e}", exc_info=True)
            await safe_edit(message, f"Ошибка перевода: {str(e)}")

    client.add_handler(MessageHandler(
        tr_handler,
        filters.command("tr", prefixes=".") & filters.me,
    ))


def on_load():
    print("[translator] Loaded. .tr [lang] <text>")
