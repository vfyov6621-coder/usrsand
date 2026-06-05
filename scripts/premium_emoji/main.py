from __future__ import annotations

"""Премиум эмоджи — grabbing, saving and sending custom animated emojis.

Requires: Telegram Premium account.
"""

import os
import json
import logging

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EMOJIS_FILE = os.path.join(SCRIPT_DIR, "emojis.json")

log = logging.getLogger("sandusr.scripts.premium_emoji")


# ───────────── config ─────────────

def _load_emojis() -> dict:
    """Load saved emojis: {name: custom_emoji_id}."""
    if os.path.exists(EMOJIS_FILE):
        try:
            with open(EMOJIS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_emojis(data: dict) -> None:
    with open(EMOJIS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ───────────── helpers ─────────────

def _extract_custom_emoji_ids(message) -> list[str]:
    """Extract all custom_emoji_id strings from message entities."""
    ids = []
    if not message.entities:
        return ids
    for ent in message.entities:
        # Pyrofork: custom_emoji_id may be a string or None
        cid = getattr(ent, "custom_emoji_id", None)
        if cid:
            ids.append(str(cid))
    return ids


def _extract_entity_info(message) -> list[dict]:
    """Return list of dicts with offset, length, custom_emoji_id."""
    result = []
    if not message.entities:
        return result
    for ent in message.entities:
        cid = getattr(ent, "custom_emoji_id", None)
        if cid:
            result.append({
                "offset": ent.offset,
                "length": ent.length,
                "custom_emoji_id": str(cid),
                "text_slice": (message.text or "")[ent.offset:ent.offset + ent.length],
            })
    return result


async def _try_get_sticker_file_id(client, custom_emoji_id: str) -> str | None:
    """Try to get a sticker file_id for a custom emoji (for preview)."""
    try:
        stickers = await client.get_custom_emoji_stickers(
            custom_emoji_ids=[int(custom_emoji_id)]
        )
        if stickers:
            return stickers[0].file_id
    except Exception as e:
        log.debug("get_custom_emoji_stickers failed for %s: %s", custom_emoji_id, e)
    return None


# ───────────── commands ─────────────

async def _cmd_help(client, message) -> None:
    """Show help."""
    from pyrogram.enums import ParseMode

    text = (
        "<b>\u2728 Премиум эмоджи</b>\n\n"
        "<code>-прем сб</code> \u2014 извлечь ID (ответ на сообщение)\n"
        "<code>-прем сох <name></code> \u2014 сохранить эмоджи\n"
        "<code>-прем сп</code> \u2014 список сохранённых\n"
        "<code>-прем уд <name></code> \u2014 удалить\n"
        "<code>-прем от <name></code> \u2014 отправить\n"
        "<code>-прем id <ID></code> \u2014 отправить по ID\n"
        "<code>-прем соо текст :имя: текст</code> \u2014 сообщение с эмоджи\n"
    )
    from scripts._utils import safe_edit
    await safe_edit(message, text, parse_mode=ParseMode.HTML)


async def _cmd_grab(client, message) -> None:
    """Reply to a message → extract all premium/custom emoji IDs."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    if not message.reply_to_message:
        await safe_edit(
            message,
            "\u274c Ответьте на сообщение с премиум эмоджи:\n<code>-прем собрать</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    reply = message.reply_to_message

    # Check entities in reply
    # Also check caption entities (for photos/documents with captions)
    entities_info = _extract_entity_info(reply)
    if reply.caption:
        cap_entities = reply.caption_entities or []
        for ent in cap_entities:
            cid = getattr(ent, "custom_emoji_id", None)
            if cid:
                text_slice = (reply.caption or "")[ent.offset:ent.offset + ent.length]
                entities_info.append({
                    "offset": ent.offset,
                    "length": ent.length,
                    "custom_emoji_id": str(cid),
                    "text_slice": text_slice,
                })

    # Also check stickers in the reply
    if reply.sticker:
        sticker_set_name = reply.sticker.set_name
        # Premium stickers can be used as custom emojis
        if sticker_set_name:
            entities_info.append({
                "offset": 0,
                "length": 0,
                "custom_emoji_id": f"sticker:{reply.sticker.file_id[:30]}...",
                "text_slice": "\U0001f3a8 (sticker)",
                "note": "This is a sticker, not a custom emoji. Use -prem save to save it.",
            })

    if not entities_info:
        await safe_edit(
            message,
            "\u2753 В сообщении нет премиум эмоджи",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"<b>\U0001f50d Найдено: {len(entities_info)} премиум эмоджи</b>\n"]
    for i, info in enumerate(entities_info, 1):
        text_repr = info.get("text_slice", "?")
        cid = info["custom_emoji_id"]
        # Truncate sticker file_ids
        if cid.startswith("sticker:"):
            lines.append(f"<b>{i}.</b> {text_repr} \u2014 <i>{cid}</i>")
        else:
            lines.append(
                f"<b>{i}.</b> {text_repr}\n"
                f"    <code>{cid}</code>"
            )

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

    await safe_edit(message, text, parse_mode=ParseMode.HTML)


async def _cmd_save(client, message) -> None:
    """Reply to a message with premium emoji → save it with a name."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_edit(
            message,
            "\u274c Использование: <code>-прем сохранить \u003cname\u003e</code> (ответ на сообщение с эмоджи)",
            parse_mode=ParseMode.HTML,
        )
        return

    name = parts[1].strip().lower()
    if not name.isalnum() and "_" not in name and "-" not in name:
        await safe_edit(
            message,
            "\u274c Имя может содержать только буквы, цифры, _ и -",
            parse_mode=ParseMode.HTML,
        )
        return

    if not message.reply_to_message:
        await safe_edit(
            message,
            "\u274c Ответьте на сообщение с премиум эмоджи",
            parse_mode=ParseMode.HTML,
        )
        return

    reply = message.reply_to_message
    ids = _extract_custom_emoji_ids(reply)
    if not ids and reply.caption_entities:
        for ent in reply.caption_entities:
            cid = getattr(ent, "custom_emoji_id", None)
            if cid:
                ids.append(str(cid))

    if not ids:
        # Check if reply is a sticker — we can try to use it as emoji
        if reply.sticker:
            try:
                stickers = await client.get_custom_emoji_stickers(
                    custom_emoji_ids=[reply.sticker.custom_emoji_id]
                ) if getattr(reply.sticker, "custom_emoji_id", None) else []
                if stickers:
                    ids.append(reply.sticker.custom_emoji_id)
            except Exception:
                pass

        if not ids:
            await safe_edit(
                message,
                "\u274c В сообщении нет премиум эмоджи",
                parse_mode=ParseMode.HTML,
            )
            return

    emoji_id = ids[0]
    data = _load_emojis()
    data[name] = emoji_id
    _save_emojis(data)

    # Try to show preview
    sticker_fid = await _try_get_sticker_file_id(client, emoji_id)
    if sticker_fid:
        try:
            await message.reply_document(
                sticker_fid,
                caption=f"\u2705 Сохранено как <code>{name}</code>\nID: <code>{emoji_id}</code>",
                parse_mode=ParseMode.HTML,
            )
            try:
                await message.delete()
            except Exception:
                pass
            return
        except Exception:
            pass

    await safe_edit(
        message,
        f"\u2705 Сохранено как <code>{name}</code>\nID: <code>{emoji_id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def _cmd_list(client, message) -> None:
    """Show all saved premium emojis."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    data = _load_emojis()
    if not data:
        await safe_edit(
            message,
            "\U0001f5c2 Список пуст. Сохраните эмоджи:\n<code>-прем сохранить \u003cname\u003e</code> (ответ на эмоджи)",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"<b>\u2728 Сохранённые эмоджи ({len(data)}):</b>\n"]
    for name, emoji_id in data.items():
        lines.append(f"  \u2022 <code>{name}</code> \u2014 <code>{emoji_id}</code>")

    text = "\n".join(lines)
    text += (
        "\n\n<i>Использование:</i>\n"
        "<code>-прем отправить \u003cname\u003e</code> \u2014 отправить эмоджи\n"
        "<code>-прем id \u003cID\u003e</code> \u2014 отправить по ID\n"
        "<code>-прем удалить \u003cname\u003e</code> \u2014 удалить"
    )

    if len(text) > 4000:
        text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

    await safe_edit(message, text, parse_mode=ParseMode.HTML)


async def _cmd_del(client, message) -> None:
    """Delete a saved emoji by name."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_edit(
            message,
            "\u274c Использование: <code>-прем удалить \u003cname\u003e</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    name = parts[1].strip().lower()
    data = _load_emojis()
    if name not in data:
        await safe_edit(
            message,
            f"\u274c Эмоджи <code>{name}</code> не найден",
            parse_mode=ParseMode.HTML,
        )
        return

    del data[name]
    _save_emojis(data)
    await safe_edit(
        message,
        f"\u2705 Удалено: <code>{name}</code>",
        parse_mode=ParseMode.HTML,
    )


async def _cmd_use(client, message) -> None:
    """Send a saved premium emoji by name."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_edit(
            message,
            "\u274c Использование: <code>-прем отправить \u003cname\u003e</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    name = parts[1].strip().lower()
    data = _load_emojis()
    if name not in data:
        await safe_edit(
            message,
            f"\u274c Эмоджи <code>{name}</code> не найден. Список: <code>-прем список</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    emoji_id = data[name]
    await _send_custom_emoji(client, message, emoji_id)


async def _cmd_send_id(client, message) -> None:
    """Send a premium emoji by custom_emoji_id directly."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_edit(
            message,
            "\u274c Использование: <code>-прем id \u003ccustom_emoji_id\u003e</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    emoji_id = parts[1].strip()
    # Validate it looks like a numeric ID
    if not emoji_id.isdigit():
        await safe_edit(
            message,
            "\u274c ID должен быть числом",
            parse_mode=ParseMode.HTML,
        )
        return

    await _send_custom_emoji(client, message, emoji_id)


async def _cmd_msg(client, message) -> None:
    """Send a message with premium emojis embedded in text.

    Usage: -prem msg Hello :fire: World :heart: end
    Where :fire: and :heart: are names of saved emojis.
    """
    from pyrogram.enums import ParseMode
    from pyrogram.types import MessageEntity
    from scripts._utils import safe_edit

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_edit(
            message,
            "\u274c Использование: <code>-прем сообщение текст :имя_эмоджи: текст</code>\n"
            "<i>Заменяет :имя: на сохранённые премиум эмоджи</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_text = parts[1]
    data = _load_emojis()

    if not data:
        await safe_edit(
            message,
            "\u2753 Сначала сохраните эмоджи: <code>-прем сохранить \u003cname\u003e</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Find all :name: patterns
    import re
    pattern = re.compile(r":(\w+):")
    matches = list(pattern.finditer(raw_text))

    if not matches:
        await safe_edit(
            message,
            "\u2753 Нет плейсхолдеров :имя: в тексте",
            parse_mode=ParseMode.HTML,
        )
        return

    entities = []
    new_text = raw_text
    offset_shift = 0

    for m in matches:
        name = m.group(1).lower()
        if name in data:
            emoji_id = data[name]
            # We replace :name: with a single unicode char as placeholder
            # The actual emoji char doesn't matter — the entity maps to custom emoji
            placeholder = "\u2764"  # heart as placeholder (will be replaced visually)
            start = m.start() - offset_shift
            end = m.end() - offset_shift

            # Replace :name: with placeholder
            new_text = new_text[:m.start()] + placeholder + new_text[m.end():]
            offset_shift += (m.end() - m.start()) - 1  # length difference

            entities.append(
                MessageEntity(
                    type="custom_emoji",
                    offset=start,
                    length=1,
                    custom_emoji_id=emoji_id,
                )
            )

    if not entities:
        await safe_edit(
            message,
            "\u2753 Ни один из плейсхолдеров не найден в сохранённых эмоджи",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        await client.send_message(
            chat_id=message.chat.id,
            text=new_text,
            entities=entities,
            reply_to_message_id=message.reply_to_message_id,
        )
        try:
            await message.delete()
        except Exception:
            pass
    except Exception as e:
        log.error("prem msg error: %s", e, exc_info=True)
        await safe_edit(
            message,
            f"\u274c Не удалось отправить: {e}",
            parse_mode=ParseMode.HTML,
        )


# ───────────── send helper ─────────────

async def _send_custom_emoji(client, message, emoji_id: str) -> None:
    """Send a single custom emoji to the current chat."""
    from pyrogram.types import MessageEntity
    from scripts._utils import safe_edit

    placeholder = "\u2764\ufe0f"
    try:
        await client.send_message(
            chat_id=message.chat.id,
            text=placeholder,
            entities=[
                MessageEntity(
                    type="custom_emoji",
                    offset=0,
                    length=len(placeholder),
                    custom_emoji_id=emoji_id,
                )
            ],
            reply_to_message_id=message.reply_to_message_id,
        )
        try:
            await message.delete()
        except Exception:
            pass
    except Exception as e:
        log.error("send_custom_emoji error: %s", e, exc_info=True)
        await safe_edit(
            message,
            f"\u274c Не удалось отправить: {e}\n"
            "<i>Возможно, у вас нет Telegram Premium</i>",
            parse_mode=ParseMode.HTML,
        )


# ───────────── dispatcher ─────────────

def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit, cmd

    async def _dispatcher(client, message: Message):
        parts = message.text.split()
        sub = parts[1] if len(parts) > 1 else ""

        try:
            if sub in ("сб", "собрать", "grab", "extract", "ids"):
                await _cmd_grab(client, message)
            elif sub in ("сох", "сохранить", "save", "add", "+"):
                await _cmd_save(client, message)
            elif sub in ("сп", "список", "list", "ls", "all"):
                await _cmd_list(client, message)
            elif sub in ("уд", "удалить", "del", "rm", "remove", "-"):
                await _cmd_del(client, message)
            elif sub in ("от", "отправить", "use", "send", "show"):
                await _cmd_use(client, message)
            elif sub in ("id", "ids"):
                await _cmd_send_id(client, message)
            elif sub in ("соо", "сообщение", "msg", "text", "write"):
                await _cmd_msg(client, message)
            else:
                await _cmd_help(client, message)
        except Exception as e:
            log.error("unhandled error: %s", e, exc_info=True)
            await safe_edit(message, f"\u274c Ошибка: {e}")

    client.add_handler(MessageHandler(
        _dispatcher,
        cmd("прем"),
    ))


def on_load():
    n = len(_load_emojis())
    print(f"[premium_emoji] Loaded ({n} saved) (-прем)")


def on_unload():
    print("[premium_emoji] Unloaded")
