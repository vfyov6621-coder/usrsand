"""Ping — simple userbot ping."""


def register(client):
    import time
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.ping")

    async def ping_handler(client, message: Message):
        try:
            start = time.time()
            await safe_edit(message, "**Pong!**")
            end = time.time()
            ms = int((end - start) * 1000)
            await safe_edit(message, f"**Pong!** `{ms}ms`")
        except Exception as e:
            log.error(f"ping error: {e}", exc_info=True)

    client.add_handler(MessageHandler(
        ping_handler,
        cmd("ping"),
    ))


def on_load():
    print("[ping] Loaded. .ping")
