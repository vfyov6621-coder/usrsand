"""
Voice Saver — сохранение и отправка голосовых сообщений
.гч с <имя>  — сохранить (ответ на голосовое / кружок)
.гч о <имя>  — отправить сохранённое гч
.гч сп       — список сохранённых
.гч у <имя>  — удалить
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(BASE_DIR)),
    "scripts_custom",
    "voices.json",
)
VOICES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(BASE_DIR)),
    "scripts_custom",
    "voice_saver",
)

os.makedirs(VOICES_DIR, exist_ok=True)


def _load() -> dict:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    @client.on_message(filters.regex(r"^\.гч(?:\s|$)") & filters.me)
    async def voice_handler(client, message: Message):
        args = message.text.split(maxsplit=2)
        # .гч без аргументов — справка
        if len(args) < 2:
            await message.edit_text(
                "<b>🎤 Голосовые сообщения</b>\n\n"
                "<code>.гч с &lt;имя&gt;</code> — сохранить (ответ на гс/гч)\n"
                "<code>.гч о &lt;имя&gt;</code> — отправить\n"
                "<code>.гч сп</code> — список\n"
                "<code>.гч у &lt;имя&gt;</code> — удалить",
                parse_mode=ParseMode.HTML,
            )
            return

        action = args[1].lower()

        # ── СПИСОК ──────────────────────────────────────────────
        if action == "сп":
            voices = _load()
            if not voices:
                await message.edit_text(
                    "🎤 Сохранённых голосовых нет.\n\n"
                    "<code>.гч с &lt;имя&gt;</code> (ответ на гс/гч)",
                    parse_mode=ParseMode.HTML,
                )
                return
            lines = []
            for name, info in sorted(voices.items()):
                kind = "🔴" if info.get("type") == "round" else "🎤"
                lines.append(f"  {kind} <code>{name}</code>")
            await message.edit_text(
                f"🎤 <b>Сохранённые ({len(voices)}):</b>\n\n"
                + "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )
            return

        # ── УДАЛИТЬ ──────────────────────────────────────────────
        if action == "у":
            if len(args) < 3:
                await message.edit_text(
                    "❌ <code>.гч у &lt;имя&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            name = args[2].strip()
            voices = _load()
            if name not in voices:
                await message.edit_text(
                    f"❌ <b>{name}</b> не найдено",
                    parse_mode=ParseMode.HTML,
                )
                return
            # удалить файл
            filepath = voices[name].get("file", "")
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            del voices[name]
            _save(voices)
            await message.edit_text(
                f"✅ <b>{name}</b> удалено",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── ОТПРАВИТЬ ────────────────────────────────────────────
        if action == "о":
            if len(args) < 3:
                await message.edit_text(
                    "❌ <code>.гч о &lt;имя&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            name = args[2].strip()
            voices = _load()
            if name not in voices:
                await message.edit_text(
                    f"❌ <b>{name}</b> не найдено",
                    parse_mode=ParseMode.HTML,
                )
                return
            filepath = voices[name].get("file", "")
            vtype = voices[name].get("type", "voice")
            if not filepath or not os.path.exists(filepath):
                await message.edit_text(
                    f"❌ Файл <b>{name}</b> не найден (удалён с диска)",
                    parse_mode=ParseMode.HTML,
                )
                return
            try:
                await message.delete()
                if vtype == "round":
                    await client.send_video_note(
                        chat_id=message.chat.id,
                        video_note=filepath,
                    )
                else:
                    await client.send_voice(
                        chat_id=message.chat.id,
                        voice=filepath,
                    )
            except Exception as e:
                await message.reply_text(
                    f"❌ Ошибка: {e}",
                    parse_mode=ParseMode.HTML,
                )
            return

        # ── СОХРАНИТЬ ─────────────────────────────────────────────
        if action == "с":
            if len(args) < 3:
                await message.edit_text(
                    "❌ <code>.гч с &lt;имя&gt;</code> (ответ на гс/гч)",
                    parse_mode=ParseMode.HTML,
                )
                return
            name = args[2].strip()
            reply = message.reply_to_message
            if not reply:
                await message.edit_text(
                    "❌ Ответьте на голосовое сообщение",
                    parse_mode=ParseMode.HTML,
                )
                return

            # определить тип: голосовое или кружок
            is_round = bool(reply.video_note)
            is_voice = bool(reply.voice)

            if not is_round and not is_voice:
                await message.edit_text(
                    "❌ В ответе должно быть голосовое или кружок",
                    parse_mode=ParseMode.HTML,
                )
                return

            await message.edit_text("🎤 Скачивание...", parse_mode=ParseMode.HTML)

            try:
                file_id = reply.video_note.file_id if is_round else reply.voice.file_id
                ext = ".ogg"
                filename = f"{name}{ext}"
                filepath = os.path.join(VOICES_DIR, filename)

                # скачать файл
                downloaded = await client.download_media(
                    file_id,
                    file_name=filepath,
                )

                if not downloaded:
                    await message.edit_text(
                        "❌ Не удалось скачать",
                        parse_mode=ParseMode.HTML,
                    )
                    return

                # сохранить метаданные
                voices = _load()
                voices[name] = {
                    "file": downloaded,
                    "type": "round" if is_round else "voice",
                }
                _save(voices)

                kind = "кружок" if is_round else "голосовое"
                await message.edit_text(
                    f"✅ {kind} <b>{name}</b> сохранено!",
                    parse_mode=ParseMode.HTML,
                )

            except Exception as e:
                await message.edit_text(
                    f"❌ Ошибка: {e}",
                    parse_mode=ParseMode.HTML,
                )
            return

        # ── НЕИЗВЕСТНАЯ КОМАНДА ──────────────────────────────────
        await message.edit_text(
            "❌ Неизвестная команда. <code>.гч</code> для справки",
            parse_mode=ParseMode.HTML,
        )


def on_load():
    print("[VoiceSaver] Loaded. .гч с/о/сп/у")
    os.makedirs(VOICES_DIR, exist_ok=True)


def on_unload():
    print("[VoiceSaver] Unloaded")
