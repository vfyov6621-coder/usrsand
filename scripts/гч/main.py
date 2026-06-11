"""гч — показывает ID пользователя, чата и ответа."""


def register(client):
    import logging
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.гч")

    async def гч_handler(client, message: Message):
        try:
            me = await client.get_me()
            my_id = me.id
            chat_id = message.chat.id

            lines = [
                f"**Ваш ID:** `{my_id}`",
                f"**ID чата:** `{chat_id}`",
            ]

            # Если ответили на сообщение — показать ID автора
            if message.reply_to_message:
                reply = message.reply_to_message
                reply_user_id = reply.from_user.id if reply.from_user else None
                if reply_user_id:
                    lines.append(f"**ID ответа:** `{reply_user_id}`")
                else:
                    lines.append("**ID ответа:** `нет (канал/аноним)`")

            await safe_edit(message, "\n".join(lines))
        except Exception as e:
            log.error(f"гч error: {e}", exc_info=True)

    client.add_handler(MessageHandler(
        гч_handler,
        cmd("гч"),
    ))


def on_load():
    print("[гч] Loaded. -гч")