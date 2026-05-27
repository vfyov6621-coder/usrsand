"""Translator — -tr [lang] <text> or reply
Uses MyMemory API (free, works without VPN, no Google).
"""

import urllib.request
import urllib.parse
import urllib.error
import json

API_URL = "https://api.mymemory.translated.net/get"


def _translate(text: str, target_lang: str = "en", source_lang: str = "auto") -> str:
    """Translate text via MyMemory API (synchronous, for run_in_executor)."""
    params = urllib.parse.urlencode({
        "q": text,
        "langpair": f"{source_lang}|{target_lang}",
    })
    url = f"{API_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated = data.get("responseData", {}).get("translatedText", "")
            if not translated:
                translated = data.get("responseData", {}).get("translatedText", "")
            if not translated:
                matches = data.get("matches", [])
                if matches:
                    translated = matches[0].get("translation", "")
            return translated or "Перевод не найден"
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "Слишком много запросов, подожди секунду и попробуй снова"
        return f"Ошибка API: {e.code}"
    except Exception as e:
        return f"Ошибка: {e}"


# Language code mapping (common codes)
_LANG_ALIASES = {
    "ru": "ru", "en": "en", "uk": "uk", "be": "be", "zh": "zh",
    "de": "de", "fr": "fr", "es": "es", "it": "it", "pt": "pt",
    "ja": "ja", "ko": "ko", "ar": "ar", "pl": "pl", "nl": "nl",
    "tr": "tr", "cs": "cs", "sv": "sv", "fi": "fi", "el": "el",
}


def register(client):
    import asyncio
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.translator")

    async def tr_handler(client, message: Message):
        try:
            args = message.text.split(maxsplit=1)

            if len(args) < 2:
                text = None
                lang = "en"
            else:
                potential_lang = args[1].split()[0] if args[1] else ""
                if len(potential_lang) == 2 and potential_lang.isalpha():
                    lang = _LANG_ALIASES.get(potential_lang.lower(), potential_lang.lower())
                    try:
                        text = args[1].split(maxsplit=1)[1]
                    except IndexError:
                        text = None
                else:
                    text = args[1]
                    lang = "en"

            if not text:
                if message.reply_to_message:
                    text = message.reply_to_message.text or message.reply_to_message.caption
                    if not text:
                        await safe_edit(message, "Нет текста для перевода")
                        return
                else:
                    await safe_edit(message,
                        "Используйте: <code>-tr [lang] &lt;текст&gt;</code>\n"
                        "Или ответьте на сообщение командой <code>-tr [lang]</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return

            # Limit text length (MyMemory max ~500 chars free)
            if len(text) > 500:
                text = text[:500]

            await safe_edit(message, "Перевод...")

            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(None, _translate, text, lang)
            await safe_edit(
                message,
                f"<b>Перевод ({lang}):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            log.error(f"translate error: {e}", exc_info=True)
            await safe_edit(message, f"Ошибка перевода: {str(e)}")

    client.add_handler(MessageHandler(
        tr_handler,
        cmd("tr"),
    ))


def on_load():
    print("[translator] Loaded. -tr [lang] <text>")
