from __future__ import annotations

"""Админ-инструменты — бан/разбан в группах, блокировка в ЛС, мут.

Требует права администратора в чате.
"""

import logging

log = logging.getLogger("sandusr.scripts.admin")


# ───────────── ban / kick ─────────────

async def _cmd_ban(client, message) -> None:
    """Бан пользователя (ответ на сообщение)."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    if not message.reply_to_message:
        await safe_edit(
            message,
            "\u274c Ответьте на сообщение пользователя\n<code>-админ бан [причина]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target = message.reply_to_message
    if not target.from_user:
        await safe_edit(message, "\u274c Нельзя забанить анонима/канал", parse_mode=ParseMode.HTML)
        return

    # Don't ban yourself
    if target.from_user.id == message.from_user.id:
        await safe_edit(message, "\u274c Нельзя забанить себя \U0001f605", parse_mode=ParseMode.HTML)
        return

    # Extract reason
    parts = message.text.split(maxsplit=1)
    reason = parts[1].strip() if len(parts) > 1 else "не указана"

    user = target.from_user
    user_tag = f"<a href=\"tg://user?id={user.id}\">{user.first_name or 'user'}</a>"

    try:
        await client.ban_chat_member(
            chat_id=message.chat.id,
            user_id=user.id,
        )
        log.info("Banned user %s (%s) in chat %s, reason: %s", user.id, user.first_name, message.chat.id, reason)

        try:
            await target.delete()
        except Exception:
            pass

        await safe_edit(
            message,
            f"\u26d4 <b>Забанен:</b> {user_tag}\n"
            f"\U0001f4cb <b>Причина:</b> <i>{reason}</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        err = str(e)
        if "admin" in err.lower() or "rights" in err.lower() or "not enough" in err.lower():
            await safe_edit(
                message,
                "\u274c Недостаточно прав для бана. Проверьте, что вы админ и бот/акк имеет права.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


async def _cmd_unban(client, message) -> None:
    """Разбан пользователя."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    parts = message.text.split(maxsplit=1)
    target_id = None

    # If reply — get user from reply
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(parts) > 1:
        # Try to parse as user ID or @username
        arg = parts[1].strip()
        if arg.isdigit():
            target_id = int(arg)
        elif arg.startswith("@"):
            try:
                resolved = await client.get_users(arg)
                target_id = resolved.id
            except Exception:
                pass
        else:
            # Maybe forwarded message has user
            if message.forward_from:
                target_id = message.forward_from.id

    if not target_id:
        await safe_edit(
            message,
            "\u274c Укажите пользователя:\n"
            "<code>-админ разбан @username</code> или <code>-админ разбан ID</code> или ответьте на сообщение",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        await client.unban_chat_member(chat_id=message.chat.id, user_id=target_id)
        log.info("Unbanned user %s in chat %s", target_id, message.chat.id)
        await safe_edit(
            message,
            f"\u2705 Пользователь <code>{target_id}</code> разбанен",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


async def _cmd_kick(client, message) -> None:
    """Кикнуть пользователя (бан + сразу разбан)."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    if not message.reply_to_message:
        await safe_edit(
            message,
            "\u274c Ответьте на сообщение пользователя\n<code>-админ кик [причина]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target = message.reply_to_message
    if not target.from_user:
        await safe_edit(message, "\u274c Нельзя кикнуть анонима/канал", parse_mode=ParseMode.HTML)
        return

    if target.from_user.id == message.from_user.id:
        await safe_edit(message, "\u274c Нельзя кикнуть себя \U0001f605", parse_mode=ParseMode.HTML)
        return

    parts = message.text.split(maxsplit=1)
    reason = parts[1].strip() if len(parts) > 1 else "не указана"

    user = target.from_user
    user_tag = f"<a href=\"tg://user?id={user.id}\">{user.first_name or 'user'}</a>"

    try:
        await client.ban_chat_member(chat_id=message.chat.id, user_id=user.id)
        await client.unban_chat_member(chat_id=message.chat.id, user_id=user.id)

        log.info("Kicked user %s (%s) from chat %s", user.id, user.first_name, message.chat.id)

        try:
            await target.delete()
        except Exception:
            pass

        await safe_edit(
            message,
            f"\U0001f4a5 <b>Кикнут:</b> {user_tag}\n"
            f"\U0001f4cb <b>Причина:</b> <i>{reason}</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


# ───────────── mute ─────────────

async def _cmd_mute(client, message) -> None:
    """Замьютить пользователя."""
    from pyrogram.enums import ChatMemberStatus
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    if not message.reply_to_message:
        await safe_edit(
            message,
            "\u274c Ответьте на сообщение пользователя\n"
            "<code>-админ мут [часы]</code> — мут навсегда\n"
            "<code>-админ мут 2</code> — мут на 2 часа\n"
            "<code>-админ мут 30m</code> — мут на 30 минут",
            parse_mode=ParseMode.HTML,
        )
        return

    target = message.reply_to_message
    if not target.from_user:
        await safe_edit(message, "\u274c Нельзя замьютить анонима/канал", parse_mode=ParseMode.HTML)
        return

    if target.from_user.id == message.from_user.id:
        await safe_edit(message, "\u274c Нельзя замьютить себя \U0001f605", parse_mode=ParseMode.HTML)
        return

    # Parse duration
    parts = message.text.split(maxsplit=1)
    duration_arg = parts[1].strip() if len(parts) > 1 else ""

    until_date = None
    duration_text = "\u043d\u0430\u0432\u0441\u0435\u0433\u0434\u0430"  # "навсегда"

    if duration_arg:
        import re
        total_seconds = 0
        match = re.match(r"^(\d+)\s*(h|hours?|ch|(\u0447\u0430\u0441\u0430?))$", duration_arg, re.IGNORECASE)
        if match:
            total_seconds = int(match.group(1)) * 3600
        else:
            match = re.match(r"^(\d+)\s*(m|min|minutes?|\u043c\u0438\u043d)", duration_arg, re.IGNORECASE)
            if match:
                total_seconds = int(match.group(1)) * 60
            else:
                match = re.match(r"^(\d+)\s*(d|days?|\u0434\u0435\u043d\u044c?)", duration_arg, re.IGNORECASE)
                if match:
                    total_seconds = int(match.group(1)) * 86400
                elif duration_arg.isdigit():
                    total_seconds = int(duration_arg) * 3600  # default: hours

        if total_seconds > 0:
            import datetime
            until_date = datetime.datetime.utcnow() + datetime.timedelta(seconds=total_seconds)
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            if h > 0 and m > 0:
                duration_text = f"\u043d\u0430 {h} \u0447 {m} \u043c\u0438\u043d"
            elif h > 0:
                duration_text = f"\u043d\u0430 {h} \u0447"
            elif m > 0:
                duration_text = f"\u043d\u0430 {m} \u043c\u0438\u043d"

    user = target.from_user
    user_tag = f"<a href=\"tg://user?id={user.id}\">{user.first_name or 'user'}</a>"

    try:
        await client.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user.id,
            permissions={"can_send_messages": False},
            until_date=until_date,
        )
        log.info("Muted user %s in chat %s, duration: %s", user.id, message.chat.id, duration_text)

        await safe_edit(
            message,
            f"\U0001f6ab <b>Замьючен:</b> {user_tag}\n"
            f"\u23f0 <b>Срок:</b> <i>{duration_text}</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


async def _cmd_unmute(client, message) -> None:
    """Размьютить пользователя."""
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await safe_edit(
            message,
            "\u274c Ответьте на сообщение пользователя\n<code>-админ размут</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user = message.reply_to_message.from_user
    user_tag = f"<a href=\"tg://user?id={user.id}\">{user.first_name or 'user'}</a>"

    try:
        await client.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user.id,
            permissions={"can_send_messages": True, "can_send_media_messages": True, "can_send_other_messages": True, "can_add_web_page_previews": True},
        )
        log.info("Unmuted user %s in chat %s", user.id, message.chat.id)
        await safe_edit(
            message,
            f"\U0001f50a <b>Размьючен:</b> {user_tag}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


# ───────────── block in DMs ─────────────

async def _cmd_block(client, message) -> None:
    """Заблокировать пользователя (в ЛС или ответ на сообщение)."""
    from pyrogram.enums import ChatType
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    # 1) In a private chat — block the person you're chatting with
    if message.chat.type == ChatType.PRIVATE:
        target_id = message.chat.id
        target_name = message.chat.first_name or "user"
    elif message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name or "user"
    else:
        # Try to parse ID or username from args
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await safe_edit(
                message,
                "\u274c В ЛС: просто <code>-админ блок</code>\n"
                "\u0412 \u0433\u0440\u0443\u043f\u043f\u0435: ответьте на сообщение или <code>-админ блок @username / ID</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        arg = parts[1].strip()
        try:
            if arg.isdigit():
                target_id = int(arg)
            elif arg.startswith("@"):
                u = await client.get_users(arg)
                target_id = u.id
                target_name = u.first_name or arg
            else:
                await safe_edit(message, "\u274c Укажите @username или ID", parse_mode=ParseMode.HTML)
                return
        except Exception as e:
            await safe_edit(message, f"\u274c Пользователь не найден: {e}", parse_mode=ParseMode.HTML)
            return

    try:
        await client.block_user(target_id)
        log.info("Blocked user %s (%s)", target_id, target_name)
        await safe_edit(
            message,
            f"\u26d4 <b>Заблокирован:</b> <code>{target_name}</code> (<code>{target_id}</code>)\n"
            "\u2705 Пользователь не сможет писать вам в ЛС",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


async def _cmd_unblock(client, message) -> None:
    """Разблокировать пользователя."""
    from pyrogram.enums import ChatType
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    # 1) In a private chat — unblock the person
    if message.chat.type == ChatType.PRIVATE:
        target_id = message.chat.id
        target_name = message.chat.first_name or "user"
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await safe_edit(
                message,
                "\u274c В ЛС: просто <code>-админ разблок</code>\n"
                "\u0412 \u0433\u0440\u0443\u043f\u043f\u0435: <code>-админ разблок @username / ID</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        arg = parts[1].strip()
        try:
            if arg.isdigit():
                target_id = int(arg)
            elif arg.startswith("@"):
                u = await client.get_users(arg)
                target_id = u.id
                target_name = u.first_name or arg
            else:
                await safe_edit(message, "\u274c Укажите @username или ID", parse_mode=ParseMode.HTML)
                return
        except Exception as e:
            await safe_edit(message, f"\u274c Не найден: {e}", parse_mode=ParseMode.HTML)
            return

    try:
        await client.unblock_user(target_id)
        log.info("Unblocked user %s (%s)", target_id, target_name)
        await safe_edit(
            message,
            f"\u2705 <b>Разблокирован:</b> <code>{target_name}</code> (<code>{target_id}</code>)",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


# ───────────── help ─────────────

async def _cmd_help(client, message) -> None:
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    text = (
        "<b>\U0001f528 Админ-инструменты</b>\n\n"
        "\U0001f534 <b>В группе</b> (требуются права админа):\n"
        "<code>-админ бан [причина]</code> \u2014 забанить (ответ на сообщение)\n"
        "<code>-админ разбан @user / ID</code> \u2014 разбанить\n"
        "<code>-админ кик [причина]</code> \u2014 кикнуть (бан + разбан)\n"
        "<code>-админ мут [2h / 30m / 1d]</code> \u2014 замьютить\n"
        "<code>-админ размут</code> \u2014 размьютить (ответ на сообщение)\n\n"
        "\U0001f535 <b>В ЛС:</b>\n"
        "<code>-админ блок</code> \u2014 заблокировать пользователя\n"
        "<code>-админ разблок</code> \u2014 разблокировать\n\n"
        "<i>В группе -админ блок/-админ разблок работают через ответ или @username</i>"
    )
    await safe_edit(message, text, parse_mode=ParseMode.HTML)


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
            if sub in ("бан",):
                await _cmd_ban(client, message)
            elif sub in ("разбан",):
                await _cmd_unban(client, message)
            elif sub in ("кик",):
                await _cmd_kick(client, message)
            elif sub in ("мут",):
                await _cmd_mute(client, message)
            elif sub in ("размут",):
                await _cmd_unmute(client, message)
            elif sub in ("блок", "block"):
                await _cmd_block(client, message)
            elif sub in ("разблок", "unblock"):
                await _cmd_unblock(client, message)
            else:
                await _cmd_help(client, message)
        except Exception as e:
            log.error("unhandled error: %s", e, exc_info=True)
            await safe_edit(message, f"\u274c Ошибка: {e}")

    client.add_handler(MessageHandler(
        _dispatcher,
        cmd("админ"),
    ))


def on_load():
    print("[admin] Loaded (-админ)")


def on_unload():
    print("[admin] Unloaded")
