"""
Voice Saver — сохранение и отправка медиафайлов
-гч с <имя>  — сохранить (ответ на гс / кружок / mp3 / mp4 / видео)
-гч о <имя>  — отправить сохранённое
-гч сп       — список сохранённых
-гч у <имя>  — удалить

mp3 автоматически пересохраняется как голосовое,
mp4 — как кружок.
"""

import os
import json
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(BASE_DIR)),
    "scripts_custom",
    "voices.json",
)

TYPE_ICONS = {
    "voice": "🎤",
    "round": "🔴",
    "audio": "🎵",
    "video": "🎬",
    "document_video": "📎",
}

TYPE_LABELS = {
    "voice": "голосовое",
    "round": "кружок",
    "audio": "аудио",
    "video": "видео",
    "document_video": "видео",
}


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


def _detect_reply_type(reply) -> tuple:
    """Определяет тип медиа. Возвращает (type_str, file_id) или (None, None)."""
    if reply.voice:
        return "voice", reply.voice.file_id
    if reply.video_note:
        return "round", reply.video_note.file_id
    if reply.audio:
        return "audio", reply.audio.file_id
    if reply.video:
        return "video", reply.video.file_id
    if reply.document:
        doc = reply.document
        mime = (doc.mime_type or "").lower()
        fname = (doc.file_name or "").lower()
        if mime.startswith("video/") or fname.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
            return "document_video", doc.file_id
        if mime.startswith("audio/") or fname.endswith((".mp3", ".ogg", ".flac", ".wav", ".aac")):
            return "audio", doc.file_id
    return None, None


def _needs_convert(vtype: str) -> bool:
    """Нужна ли переконвертация файла."""
    return vtype in ("audio", "video", "document_video")


async def _convert_and_get_fid(client, reply, vtype: str) -> str:
    """Скачивает файл и переконвертирует: audio→voice, video→round.
    Возвращает новый file_id."""
    # скачать во временный файл
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
    tmp_path = tmp.name
    tmp.close()

    try:
        if vtype == "audio":
            await reply.download(file_name=tmp_path)
        elif vtype in ("video", "document_video"):
            await reply.download(file_name=tmp_path)
    except Exception:
        os.unlink(tmp_path)
        raise

    try:
        # загрузить как нужный тип в "Избранное" и получить file_id
        me = await client.get_me()
        if vtype == "audio":
            msg = await client.send_voice(
                chat_id=me.id,
                voice=tmp_path,
            )
            new_type = "voice"
        else:
            msg = await client.send_video_note(
                chat_id=me.id,
                video_note=tmp_path,
            )
            new_type = "round"

        new_fid = msg.voice.file_id if new_type == "voice" else msg.video_note.file_id

        # удалить сообщение из избранного
        try:
            await msg.delete()
        except Exception:
            pass

        return new_fid, new_type
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def _send_saved(client, chat_id, fid, vtype):
    """Отправляет сохранённый файл по типу."""
    if vtype == "round":
        await client.send_video_note(chat_id=chat_id, video_note=fid)
    elif vtype == "voice":
        await client.send_voice(chat_id=chat_id, voice=fid)
    elif vtype == "audio":
        await client.send_audio(chat_id=chat_id, audio=fid)
    elif vtype in ("video", "document_video"):
        await client.send_video(chat_id=chat_id, video=fid)
    else:
        await client.send_document(chat_id=chat_id, document=fid)


def register(client):
    import asyncio
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    @client.on_message(filters.regex(r"^[-/]гч(?:\s|$)") & filters.me)
    async def voice_handler(client, message: Message):
        args = message.text.split(maxsplit=2)

        # -гч без аргументов — справка
        if len(args) < 2:
            await safe_edit(message,
                "<b>📦 Сохранение медиа</b>\n\n"
                "<code>-гч с &lt;имя&gt;</code> — сохранить (гс/кружок/mp3/mp4)\n"
                "<code>-гч о &lt;имя&gt;</code> — отправить\n"
                "<code>-гч сп</code> — список\n"
                "<code>-гч у &lt;имя&gt;</code> — удалить",
                parse_mode=ParseMode.HTML,
            )
            return

        action = args[1].lower()

        # ── СПИСОК ──────────────────────────────────────────────
        if action == "сп":
            voices = _load()
            if not voices:
                await safe_edit(message,
                    "📦 Сохранённых медиа нет.\n\n"
                    "<code>-гч с &lt;имя&gt;</code> (ответ на медиа)",
                    parse_mode=ParseMode.HTML,
                )
                return
            lines = []
            for name, info in sorted(voices.items()):
                t = info.get("type", "voice")
                icon = TYPE_ICONS.get(t, "📎")
                lines.append(f"  {icon} <code>{name}</code>")
            await safe_edit(message,
                f"📦 <b>Сохранённые ({len(voices)}):</b>\n\n"
                + "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )
            return

        # ── УДАЛИТЬ ──────────────────────────────────────────────
        if action == "у":
            if len(args) < 3:
                await safe_edit(message,
                    "❌ <code>-гч у &lt;имя&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            name = args[2].strip()
            voices = _load()
            if name not in voices:
                await safe_edit(message,
                    f"❌ <b>{name}</b> не найдено",
                    parse_mode=ParseMode.HTML,
                )
                return
            del voices[name]
            _save(voices)
            await safe_edit(message,
                f"✅ <b>{name}</b> удалено",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── ОТПРАВИТЬ ────────────────────────────────────────────
        if action == "о":
            if len(args) < 3:
                await safe_edit(message,
                    "❌ <code>-гч о &lt;имя&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            name = args[2].strip()
            voices = _load()
            if name not in voices:
                await safe_edit(message,
                    f"❌ <b>{name}</b> не найдено",
                    parse_mode=ParseMode.HTML,
                )
                return

            fid = voices[name].get("file_id", "")
            vtype = voices[name].get("type", "voice")

            if not fid:
                await safe_edit(message,
                    f"❌ file_id <b>{name}</b> отсутствует",
                    parse_mode=ParseMode.HTML,
                )
                return

            # удалить команду
            try:
                await message.delete()
            except Exception:
                pass

            # отправить
            try:
                await _send_saved(client, message.chat.id, fid, vtype)
            except Exception as e:
                err_name = type(e).__name__
                if "Slowmode" in err_name or "Flood" in err_name:
                    await asyncio.sleep(getattr(e, "value", 2) or 2)
                    try:
                        await _send_saved(client, message.chat.id, fid, vtype)
                    except Exception:
                        pass
                else:
                    await client.send_message(
                        chat_id=message.chat.id,
                        text=f"❌ Ошибка: {e}",
                        parse_mode=ParseMode.HTML,
                    )
            return

        # ── СОХРАНИТЬ ─────────────────────────────────────────────
        if action == "с":
            if len(args) < 3:
                await safe_edit(message,
                    "❌ <code>-гч с &lt;имя&gt;</code> (ответ на медиа)",
                    parse_mode=ParseMode.HTML,
                )
                return
            name = args[2].strip()
            reply = message.reply_to_message
            if not reply:
                await safe_edit(message,
                    "❌ Ответьте на медиафайл",
                    parse_mode=ParseMode.HTML,
                )
                return

            vtype, file_id = _detect_reply_type(reply)
            if not vtype or not file_id:
                await safe_edit(message,
                    "❌ В ответе должно быть голосовое, кружок, аудио (mp3) или видео (mp4)",
                    parse_mode=ParseMode.HTML,
                )
                return

            save_type = vtype

            # переконвертация: mp3→голосовое, mp4→кружок
            if _needs_convert(vtype):
                await safe_edit(message,"⏳ Переконвертация...")
                try:
                    file_id, save_type = await _convert_and_get_fid(client, reply, vtype)
                except Exception as e:
                    await safe_edit(message,
                        f"❌ Ошибка конвертации: {e}",
                        parse_mode=ParseMode.HTML,
                    )
                    return

            voices = _load()
            voices[name] = {
                "file_id": file_id,
                "type": save_type,
            }
            _save(voices)

            label = TYPE_LABELS.get(save_type, save_type)
            await safe_edit(message,
                f"✅ {label} <b>{name}</b> сохранено!",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── НЕИЗВЕСТНАЯ КОМАНДА ──────────────────────────────────
        await safe_edit(message,
            "❌ Неизвестная команда. <code>-гч</code> для справки",
            parse_mode=ParseMode.HTML,
        )


def on_load():
    print("[VoiceSaver] Loaded. -гч с/о/сп/у")


def on_unload():
    print("[VoiceSaver] Unloaded")