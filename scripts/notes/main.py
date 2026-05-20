"""Notes — quick notes in Telegram. .note save/get/list/del/set, .n <name>"""

import json
import os
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from scripts._utils import safe_edit

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "scripts_custom")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")


def _load():
    try:
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def register(client):
    @client.on_message(filters.command("note", prefixes=".") & filters.me)
    async def note_handler(client, message: Message):
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await safe_edit(message,
                "<b>📝 Заметки</b>\n\n"
                "<code>.note save &lt;имя&gt; &lt;текст&gt;</code>\n"
                "<code>.note set &lt;имя&gt;</code> (ответ на соо)\n"
                "<code>.note get &lt;имя&gt;</code>\n"
                "<code>.note list</code>\n"
                "<code>.note del &lt;имя&gt;</code>\n\n"
                "<code>.n &lt;имя&gt;</code> — быстрый вызов",
                parse_mode=ParseMode.HTML,
            )
            return

        action = args[1].lower()

        if action == "list":
            notes = _load()
            if not notes:
                await safe_edit(message, "📝 Заметок нет.\n\n<code>.note save имя текст</code>", parse_mode=ParseMode.HTML)
                return
            lines = "\n".join(f"  {i}. <code>{k}</code>" for i, k in enumerate(sorted(notes.keys()), 1))
            await safe_edit(message, f"📝 <b>Заметки ({len(notes)}):</b>\n\n{lines}", parse_mode=ParseMode.HTML)
            return

        if action == "del":
            if len(args) < 3:
                await safe_edit(message, "❌ <code>.note del &lt;имя&gt;</code>", parse_mode=ParseMode.HTML)
                return
            name = args[2].strip()
            notes = _load()
            if name in notes:
                del notes[name]
                _save(notes)
                await safe_edit(message, f"✅ Заметка <b>{name}</b> удалена", parse_mode=ParseMode.HTML)
            else:
                await safe_edit(message, f"❌ Заметка <b>{name}</b> не найдена", parse_mode=ParseMode.HTML)
            return

        if action == "get":
            if len(args) < 3:
                await safe_edit(message, "❌ <code>.note get &lt;имя&gt;</code>", parse_mode=ParseMode.HTML)
                return
            name = args[2].strip()
            notes = _load()
            if name in notes:
                await safe_edit(message, f"📝 <b>{name}:</b>\n\n{notes[name]}", parse_mode=ParseMode.HTML)
            else:
                await safe_edit(message, f"❌ Заметка <b>{name}</b> не найдена", parse_mode=ParseMode.HTML)
            return

        if action == "set":
            if len(args) < 3:
                await safe_edit(message, "❌ <code>.note set &lt;имя&gt;</code> (ответ на соо)", parse_mode=ParseMode.HTML)
                return
            name = args[2].strip()
            reply = message.reply_to_message
            if not reply:
                await safe_edit(message, "❌ Ответьте на сообщение", parse_mode=ParseMode.HTML)
                return
            text = reply.text or reply.caption or ""
            if not text:
                await safe_edit(message, "❌ Нет текста в ответе", parse_mode=ParseMode.HTML)
                return
            notes = _load()
            notes[name] = text
            _save(notes)
            await safe_edit(message, f"✅ Заметка <b>{name}</b> сохранена", parse_mode=ParseMode.HTML)
            return

        if action == "save":
            if len(args) < 3:
                await safe_edit(message, "❌ <code>.note save &lt;имя&gt; &lt;текст&gt;</code>", parse_mode=ParseMode.HTML)
                return
            rest = args[2].strip()
            parts = rest.split(maxsplit=1)
            name = parts[0]
            text = parts[1] if len(parts) > 1 else ""
            if not text:
                await safe_edit(message, "❌ Укажите текст", parse_mode=ParseMode.HTML)
                return
            notes = _load()
            notes[name] = text
            _save(notes)
            await safe_edit(message, f"✅ Заметка <b>{name}</b> сохранена", parse_mode=ParseMode.HTML)
            return

        await safe_edit(message, "❌ Неизвестное действие. .note для справки", parse_mode=ParseMode.HTML)

    @client.on_message(filters.command("n", prefixes=".") & filters.me)
    async def n_shortcut(client, message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return
        name = args[1].strip()
        notes = _load()
        if name in notes:
            await safe_edit(message, f"📝 <b>{name}:</b>\n\n{notes[name]}", parse_mode=ParseMode.HTML)
        else:
            await safe_edit(message, f"❌ Заметка <b>{name}</b> не найдена", parse_mode=ParseMode.HTML)


def on_load():
    print("[notes] Loaded. .note save/get/list/del/set, .n")
