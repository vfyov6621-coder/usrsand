"""Antimat — заменяет мат на звёздочки в чужих сообщениях + нравоучение."""

import os
import re
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

# Русский мат
BAD_WORDS = [
    "бля", "блять", "пизд", "пиздец", "пиздец", "ебан", "ебать", "ебла",
    "хуй", "хуё", "хуя", "хуев", "хуйн", "хую",
    "жоп", "жопа", "жопу", "жопе",
    "дерьм", "дерьмо",
    "мудак", "мудила", "мудил",
    "сука", "сук", "суки",
    "идиот", "дурачок", "дебил",
    "задолбал", "заебал", "достал",
    "чёрт", "черт", "блин", "бля",
    "пипец", "косяк", "каша",
]

# Шаблоны для regex (с корневыми формами)
_PATTERNS = [
    re.compile(r"еб[ауио]н", re.IGNORECASE),
    re.compile(r"п[ие]зд", re.IGNORECASE),
    re.compile(r"ху[йёеяию]", re.IGNORECASE),
    re.compile(r"бл[яья]", re.IGNORECASE),
    re.compile(r"сука", re.IGNORECASE),
    re.compile(r"дерьмо", re.IGNORECASE),
    re.compile(r"жоп[ауеы]", re.IGNORECASE),
    re.compile(r"муда[кичл]", re.IGNORECASE),
    re.compile(r"идиот", re.IGNORECASE),
    re.compile(r"дебил", re.IGNORECASE),
    re.compile(r"за[её]бал", re.IGNORECASE),
]

TAUNTS = [
    "фи, как некультурно",
    "надо ртом мыть чаще",
    "срамишься, а? 😏",
    "мама бы не одобрила",
    "пойди гуляй, парень",
    "вся надежда на мыло...",
    "автор, выйдешь и зайди нормально",
    "иногда лучше помолчать, знаешь ли",
    " filter_active= True",
    "модераторы уже в пути 🔫",
    "зачем ты так со словами-то",
    "и это тебе скажут в суде",
    "а ну-ка быстро извинись",
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


def _censor(text: str) -> tuple[str, bool]:
    """Replace bad words with asterisks. Returns (cleaned_text, was_dirty)."""
    dirty = False
    for pat in _PATTERNS:
        matches = pat.findall(text)
        if matches:
            dirty = True
        text = pat.sub(lambda m: "*" * len(m.group()), text)
    return text, dirty


def register(client):
    import logging
    import random
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.antimat")

    async def _filter_msg(client, message: Message):
        """Check incoming messages for profanity."""
        cfg = _load_cfg()
        if not cfg.get("enabled", True):
            return

        if not message.text or message.from_user.is_self:
            return

        cleaned, dirty = _censor(message.text)
        if dirty and cleaned != message.text:
            taunt = random.choice(TAUNTS)
            try:
                await message.reply_text(
                    f"✨ <code>{cleaned}</code>\n\n<i>{taunt}</i>",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception as e:
                log.debug("antimat reply error: %s", e)

    async def _antimat_cmd(client, message: Message):
        parts = message.text.split()
        arg = parts[1] if len(parts) > 1 else ""

        cfg = _load_cfg()

        if arg == "off":
            cfg["enabled"] = False
            _save_cfg(cfg)
            await safe_edit(message, "🧹 Анти-мат выключен", parse_mode=ParseMode.HTML)
        elif arg == "on":
            cfg["enabled"] = True
            _save_cfg(cfg)
            await safe_edit(message, "🧹 Анти-мат включён", parse_mode=ParseMode.HTML)
        else:
            on = cfg.get("enabled", True)
            status = "включён" if on else "выключен"
            await safe_edit(message,
                f"🧹 <b>Анти-мат</b>\n\n"
                f"Статус: {status}\n\n"
                f"<code>-antimat on</code>\n"
                f"<code>-antimat off</code>",
                parse_mode=ParseMode.HTML,
            )

    # Monitor all incoming messages
    client.add_handler(MessageHandler(
        _filter_msg,
        filters.incoming & ~filters.me & ~filters.bot & filters.text,
    ))

    # Command
    client.add_handler(MessageHandler(
        _antimat_cmd,
        filters.command("antimat", prefixes="-") & filters.me,
    ))


def on_load():
    print("[antimat] Loaded. -antimat on/off")
