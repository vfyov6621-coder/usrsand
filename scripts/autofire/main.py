"""Autofire — авто-реакция 🔥 на длинные сообщения (>50 символов)."""

import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

FIRE_EMOJIS = ["🔥", "💯", "⚡", "👁", "🏆"]


def _load_cfg() -> dict:
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": True, "min_len": 50}


def _save_cfg(cfg: dict) -> None:
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def register(client):
    import logging
    import random
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.autofire")

    async def _fire_handler(client, message: Message):
        """React 🔥 to long incoming messages."""
        cfg = _load_cfg()
        if not cfg.get("enabled", True):
            return
        if message.from_user.is_self:
            return
        if not message.text:
            return

        min_len = cfg.get("min_len", 50)
        if len(message.text) < min_len:
            return

        emoji = random.choice(FIRE_EMOJIS)
        try:
            await message.react(emoji)
        except Exception:
            pass

    async def _autofire_cmd(client, message: Message):
        parts = message.text.split()
        arg = parts[1] if len(parts) > 1 else ""

        cfg = _load_cfg()

        if arg == "off":
            cfg["enabled"] = False
            _save_cfg(cfg)
            await safe_edit(message, "🔥 Авто-реакция выключена", parse_mode=ParseMode.HTML)
        elif arg == "on":
            cfg["enabled"] = True
            _save_cfg(cfg)
            await safe_edit(message, "🔥 Авто-реакция включена", parse_mode=ParseMode.HTML)
        else:
            on = cfg.get("enabled", True)
            ml = cfg.get("min_len", 50)
            status = "включена" if on else "выключена"
            await safe_edit(message,
                f"🔥 <b>Авто-реакция</b>\n\n"
                f"Статус: {status}\n"
                f"Минимум символов: {ml}\n\n"
                f"<code>-автоогонь on</code>\n"
                f"<code>-автоогонь off</code>",
                parse_mode=ParseMode.HTML,
            )

    # Monitor all incoming messages
    client.add_handler(MessageHandler(
        _fire_handler,
        filters.incoming & ~filters.me & ~filters.bot & filters.text,
    ))

    # Command
    client.add_handler(MessageHandler(
        _autofire_cmd,
        cmd("автоогонь"),
    ))


def on_load():
    print("[autofire] Loaded. -автоогонь on/off")
