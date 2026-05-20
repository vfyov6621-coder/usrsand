"""Ping — simple userbot ping."""


def register(client):
    import time
    from pyrogram import filters
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    @client.on_message(filters.command("ping", prefixes=".") & filters.me)
    async def ping_handler(client, message: Message):
        start = time.time()
        await safe_edit(message, "**Pong!**")
        end = time.time()
        ms = int((end - start) * 1000)
        await safe_edit(message, f"**Pong!** `{ms}ms`")


def on_load():
    print("[ping] Loaded. .ping")
