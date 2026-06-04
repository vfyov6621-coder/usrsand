"""Subtitles — voice messages → text with terrible errors + laughs."""

import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

# Типичные ошибки распознавания (замены)
MISHEARS = [
    ("привет", "превет"),
    ("здравствуйте", "дравствуйти"),
    ("пожалуйста", "пажалуста"),
    ("спасибо", "спасиба"),
    ("да", "дя"),
    ("нет", "нат"),
    ("хорошо", "харашо"),
    ("как", "кок"),
    ("но", "на"),
    ("что", "што"),
    ("сейчас", "сейчяс"),
    ("может", "можит"),
    ("вообще", "вооще"),
    ("тоже", "тачже"),
    ("очень", "очинь"),
    ("потом", "патам"),
    ("говорить", "гаварить"),
    ("сделать", "здилать"),
    ("будет", "бутит"),
    ("нормально", "нормална"),
    ("собака", "сабака"),
    ("работа", "рабата"),
    ("сегодня", "сидня"),
    ("завтра", "завтра"),
    ("после", "после"),
    ("перед", "перед"),
    ("мужчина", "мужчина"),
    ("женщина", "женщина"),
    ("ребята", "рибята"),
    ("короче", "кароче"),
    ("конечно", "канешна"),
    ("правильно", "правилна"),
    ("наконец", "наконец"),
    ("например", "напримир"),
    ("просто", "праста"),
    ("например", "напримир"),
    ("вместе", "вмисте"),
    ("между", "мижду"),
    ("деревня", "диревна"),
    ("земля", "земля"),
    ("небо", "ниба"),
    (" вода", " вада"),
    ("огонь", "агонь"),
    ("дорога", "дарага"),
    ("машина", "машина"),
    ("человек", "чилавик"),
    ("программа", "праграма"),
    ("интернет", "интирнит"),
    ("телефон", "тилифон"),
    ("камера", "камира"),
    ("магазин", "магизин"),
    ("каникулы", "каникулы"),
    ("работа", "работа"),
    ("домой", "дамой"),
    ("ругается", "ругаится"),
    ("понимаю", "пинимаю"),
    ("послушай", "паслушай"),
    ("погода", "пагода"),
    ("еда", "еда"),
    ("брат", "брат"),
    ("мама", "мама"),
    ("папа", "папа"),
]

LAUGHS = [
    " хахаха",
    " ахахах",
    " хддд",
    " ахахахах",
    " лмао",
    " хехе",
    " ммм тут точно не так было сказано",
    " ну или както так",
    " (не понял ни слова но ок)",
    " как я это вообще услышал",
    " +- такое и сказал",
    " хд",
    " кхм... ну да",
    " тут явно не это было",
    " субтитры сюда бы",
]


def _load_cfg() -> dict:
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": True}


def _save_cfg(cfg: dict) -> None:
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _ruin_text(text: str) -> str:
    """Make text look like terrible speech recognition."""
    import random
    ruined = text.lower()
    # Apply mishears
    for original, wrong in MISHEARS:
        ruined = ruined.replace(original, wrong)
    # Randomly drop/change some chars (5% chance per character)
    chars = list(ruined)
    for i in range(len(chars)):
        if random.random() < 0.05 and chars[i].isalpha():
            chars[i] = random.choice("абвгдежзиклмнопрстуфхцчшщэюя")
    ruined = "".join(chars)
    # Add random punctuation
    if random.random() < 0.4:
        ruined += random.choice(["...", "..", "...?", "?!"])
    # Add laugh
    if random.random() < 0.5:
        ruined += random.choice(LAUGHS)
    return ruined


def register(client):
    import logging
    import random
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.subtitles")

    async def _voice_handler(client, message: Message):
        """React to voice messages with 'terrible transcription'."""
        cfg = _load_cfg()
        if not cfg.get("enabled", True):
            return

        if not message.voice and not message.audio:
            return
        if message.from_user.is_self:
            return

        # Fake "processing"
        duration = message.voice.duration if message.voice else 0

        # Generate fake gibberish text
        if duration and duration > 1:
            # Longer voice = longer fake text
            word_count = min(int(duration * 2), 20)
            ru_words = [
                "ну", "типа", "короче", "вот", "это", "да", "нет", "там",
                "слушай", "вообще", "ну", "значит", "типо", "просто",
                "ага", "угу", "не", "ну", "ладно", "ваще", "блин",
            ]
            fake = " ".join(random.choice(ru_words) for _ in range(word_count))
        else:
            fake = "а а а ну да нет"

        ruined = _ruin_text(fake)

        try:
            await message.reply_text(
                f"📝 <i>{ruined}</i>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.debug("sub error: %s", e)

    async def _sub_cmd(client, message: Message):
        parts = message.text.split()
        arg = parts[1] if len(parts) > 1 else ""

        cfg = _load_cfg()

        if arg == "off":
            cfg["enabled"] = False
            _save_cfg(cfg)
            await safe_edit(message, "📝 Субтитры выключены", parse_mode=ParseMode.HTML)
        elif arg == "on":
            cfg["enabled"] = True
            _save_cfg(cfg)
            await safe_edit(message, "📝 Субтитры включены", parse_mode=ParseMode.HTML)
        else:
            on = cfg.get("enabled", True)
            status = "включены" if on else "выключены"
            await safe_edit(message,
                f"📝 <b>Субтитры</b>\n\n"
                f"Статус: {status}\n\n"
                f"<code>-субтитры on</code>\n"
                f"<code>-субтитры off</code>",
                parse_mode=ParseMode.HTML,
            )

    # Monitor voice messages
    client.add_handler(MessageHandler(
        _voice_handler,
        filters.incoming & ~filters.me & ~filters.bot,
    ))

    # Command
    client.add_handler(MessageHandler(
        _sub_cmd,
        cmd("субтитры"),
    ))


def on_load():
    print("[subtitles] Loaded. -субтитры on/off")
