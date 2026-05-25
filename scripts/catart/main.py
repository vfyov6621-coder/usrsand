"""CatArt — ASCII-арт с котами. -catart [номер]"""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

CATS = [
    # 1 — сидящий
    (
        "  /\\_/\\ \n"
        " ( o.o )\n"
        "  > ^ <\n"
        " /|   |\\\n"
        "(_|   |_)"
    ),
    # 2 — спящий
    (
        "      /\\___/\\\n"
        "     (  o o  )\n"
        "     (  =^=  )\n"
        "      )     (\n"
        "     (       )\n"
        "    ( (  )  ( )\n"
        "   (__(__)__(__)"
    ),
    # 3 — грустный
    (
        "  /\\_/\\\n"
        " ( -.- )\n"
        "  (   )\n"
        "  m   m"
    ),
    # 4 — удивлённый
    (
        "  /\\_/\\\n"
        " ( O.O )\n"
        "  >   <\n"
        " /|   |\\\n"
        "(_|   |_)"
    ),
    # 5 — с рыбой
    (
        "  /\\_/\\     \n"
        " ( o.o ) />\n"
        "  > ^ <\\\n"
        " /|   |  \\\\\n"
        "(_|   |_)"
    ),
    # 6 — шпион
    (
        "   /\\_/\\\n"
        "  ( ._. )\n"
        "   > ^ <\n"
        "  /|   |\\\n"
        " ( |   | )\n"
        "  ||_O_||\n"
        "  {_____}"
    ),
    # 7 — танцующий
    (
        "    /\\_/\\\n"
        "   ( ^.^ )\n"
        "    > - <\n"
        "   /|   |\\\n"
        "  (_|   |_)\n"
        "   /\\   /\\\n"
        "  /  \\ /  \\"
    ),
    # 8 — коробка
    (
        "    /\\_/\\\n"
        "   ( o.o )\n"
        "    > ^ <\n"
        "  __|_|_|_\\\n"
        " /         \\\n"
        "|  CAT BOX  |\n"
        " \\_________/"
    ),
    # 9 — охотник
    (
        "     /\\_/\\\n"
        "    ( o.o )\n"
        "     > ^ <\n"
        "    /|   |\\\n"
        "   (_|   |_)\n"
        "  //|   |\\\\\n"
        " //|   |\\\\\n"
        "WW||   ||WW"
    ),
    # 10 — маленький
    (
        " /\\_/\\\n"
        "( o.o )\n"
        " > ^ <"
    ),
    # 11 — два кота
    (
        " /\\_/\\   /\\_/\\\n"
        "( o.o ) ( -.- )\n"
        " > ^ <   m   m"
    ),
    # 12 — инопланетный
    (
        "  /\\_/\\\n"
        " ( X.X )\n"
        "  > ~ <\n"
        " /| * |\\\n"
        "(_|   |_)"
    ),
    # 13 — толстый
    (
        "    /\\_____/\\\n"
        "   /  o   o  \\\n"
        "  ( ==  ^  == )\n"
        "   )         (\n"
        "  (           )\n"
        " ( (  )   (  ) )\n"
        "(__(__)___(__)__) "
    ),
    # 14 — злой
    (
        "  /\\_/\\\n"
        " ( >.< )\n"
        "  >!!!<\n"
        " /|   |\\\n"
        "(_|   |_)"
    ),
    # 15 — привет
    (
        "  /\\_/\\\n"
        " ( ^w^ )\n"
        "  > - <\n"
        " /|   |\\\n"
        "(_|   |_)\n"
        "\n Hello, hooman!"
    ),
    # 16 — ленивый
    (
        "   _____\n"
        "  /     \\\n"
        " |  o o  |\n"
        " |  ^_^  |\n"
        "  \\_____/\n"
        "   || ||\n"
        " zzzZZZ"
    ),
    # 17 — upside down
    (
        " (_|   |_)\n"
        " \\|   |/\n"
        "  v   v\n"
        " ( O.o )\n"
        "  \\\\_/"
    ),
    # 18 — with heart
    (
        "  /\\_/\\\n"
        " ( ._. )  <3\n"
        "  > w <\n"
        " /|   |\\\n"
        "(_|   |_)"
    ),
    # 19 — hacker
    (
        "  /\\_/\\\n"
        " ( 0 1 )\n"
        "  > >< <\n"
        " /| | |\\\n"
        "(_|_|_|_)"
    ),
    # 20 — waving
    (
        "  /\\_/\\  \n"
        " ( ^.^ )/\n"
        "  > - <\n"
        " /|   |\\\n"
        "(_|   |_)"
    ),
]


def _load_cfg() -> dict:
    import json
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": True}


def _save_cfg(cfg: dict) -> None:
    import json
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def register(client):
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.catart")

    async def _catart_cmd(client, message: Message):
        parts = message.text.split()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cfg = _load_cfg()

            # -catart (no arg) → random
            if not arg:
                import random
                cat = random.choice(CATS)
                await safe_edit(message, f"<pre>{cat}</pre>", parse_mode=ParseMode.HTML)
                return

            # -catart off
            if arg == "off":
                cfg["enabled"] = False
                _save_cfg(cfg)
                await safe_edit(message, "🐱 Кото-арт выключен", parse_mode=ParseMode.HTML)
                return

            # -catart on
            if arg == "on":
                cfg["enabled"] = True
                _save_cfg(cfg)
                await safe_edit(message, "🐱 Кото-арт включён", parse_mode=ParseMode.HTML)
                return

            # -catart N → specific cat
            try:
                n = int(arg)
            except ValueError:
                total = len(CATS)
                await safe_edit(message,
                    f"❌ Укажи номер от 1 до {total}\n"
                    f"<code>-catart</code> — рандом\n"
                    f"<code>-catart 3</code> — конкретный",
                    parse_mode=ParseMode.HTML,
                )
                return

            if n < 1 or n > len(CATS):
                await safe_edit(message,
                    f"❌ Номер от 1 до {len(CATS)}",
                    parse_mode=ParseMode.HTML,
                )
                return

            cat = CATS[n - 1]
            await safe_edit(message, f"<pre>{cat}</pre>", parse_mode=ParseMode.HTML)

        except Exception as e:
            log.error("catart error: %s", e, exc_info=True)

    client.add_handler(MessageHandler(
        _catart_cmd,
        filters.command("catart", prefixes="-") & filters.me,
    ))


def on_load():
    print(f"[catart] Loaded. {len(CATS)} котов. -catart")
