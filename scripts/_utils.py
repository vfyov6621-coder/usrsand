"""
Shared utilities for sandusr scripts.
Import: from scripts._utils import safe_edit, cmd
"""

import os
import re
import sys

# Ensure project root is in sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


def cmd(*commands):
    """Create a filter for custom-prefix commands that works in groups.

    Pyrogram's ``filters.command`` ignores custom prefixes (like ``-``) in
    group chats because Telegram only creates BOT_COMMAND entities for ``/``.
    This helper uses a regex so the command is recognised everywhere.

    Usage::

        from pyrogram import filters
        from scripts._utils import cmd

        client.add_handler(MessageHandler(
            my_handler,
            cmd("ям") & filters.me,
        ))
    """
    from pyrogram import filters
    escaped = "|".join(re.escape(c) for c in commands)
    return filters.regex(r"^[-/](" + escaped + r")\b") & filters.me


def cmd_neg(*commands):
    """Negative match — filters *out* messages that are one of the given commands.

    Example: ``filters.me & cmd_neg("ии")`` — my messages that are NOT ``-ии``.
    """
    from pyrogram import filters
    escaped = "|".join(re.escape(c) for c in commands)
    return filters.regex(r"^[-/](" + escaped + r")\b")


async def safe_edit(message, text, **kwargs):
    """
    Safe edit_text with fallback to reply.

    If the message is a **command** (starts with ``-`` or ``/``) that was
    sent as a reply to another message, the result will be sent as a reply
    to that original message (and the command message is deleted).

    Subsequent calls with the *result* message just edit it normally,
    because it no longer starts with ``-`` / ``/``.
    """
    _is_command = bool(
        message.text
        and message.text.lstrip()[:1] in "-/"
    )

    # Команда-ответ → удалить команду, ответить на оригинал
    if _is_command and message.reply_to_message:
        try:
            await message.delete()
        except Exception:
            pass
        try:
            return await message.reply_to_message.reply(text, quote=True, **kwargs)
        except Exception:
            try:
                return await message.reply(text, quote=False, **kwargs)
            except Exception:
                pass
        return None

    # Обычный случай — редактируем своё сообщение
    try:
        return await message.edit_text(text, **kwargs)
    except Exception:
        try:
            return await message.reply(text, quote=False, **kwargs)
        except Exception:
            pass
    return None
