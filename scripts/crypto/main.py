"""Crypto — бесполезный токен + курс к хлебу."""

import os
import json
import random
import string

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

ADJECTIVES = [
    "Секретный", "Мега", "Ультра", "ДUPER", "Нео", "Гипер", "Мини", "Турбо",
    "Крипто", "Велью", "Смарт", "Дарк", "Лайт", "Про", "Макс", "Нуар",
    "Эпик", "Легенда", "Имба", "Топ", "Дзен", "Премиум", "Золотой", "Базовый",
    "Дикий", "Редкий", "Артефактный", "Мифический", "Простой",
]

NOUNS = [
    "Коин", "Токен", "Биток", "Доге", "Флёф", "Котик", "Пельмень",
    "Батон", "Самовар", "Борщ", "Дед", "Мопс", "Енот", "Капибара",
    "Васаби", "Перец", "Пельмень", "Чебурек", "Котлета", "Беляш",
    "Мёд", "Гриб", "Кабан", "Хомяк", "Ленивец", "Наруто", "Суши",
    "Рамен", "Такояки", "Масала", "Фалафель", "Халва", "Шаурма",
    "Ротация", "Хайп", "Памп", "Дамп", "Вessel", "Pump",
]

SUFFIXES = [
    "Coin", "Token", "Fi", "Swap", "Inu", "Finance", "Chain",
    "Swap", "Moon", "Mars", "Rocket", "Pump", "DAO", "Lab",
    "X", "AI", "GO", "RUN", "FLY", "WIN",
]

COMMENTS = [
    " Whale activity detected!",
    " El Salvador добавил в казну",
    " Резко вырос на 3000%",
    " Девелопер продал все токены",
    " Партнёрство с KFC подтверждено",
    " Reddit залил",
    " Выгорание на минималках",
    " Прогноз: к концу года — ЛУНА",
    " Не финансовая рекомендация (нет)",
    " Рискнул — не рискнул?",
    " Памп уже начался, успевай",
    " Коррекция временна, diamond hands",
    " Ходл или фомо — вот вопрос",
    " Масштабирование через floor price",
    " TVL вырос в 5 раз за ночь",
]


def _gen_name() -> str:
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adj}{noun}"


def _gen_ticker(name: str) -> str:
    # Take first letters
    parts = name.replace(" ", "")
    if len(parts) >= 4:
        ticker = (parts[0] + random.choice(parts[1:]) + random.choice(parts[2:]) + random.choice(parts[3:])).upper()
    elif len(parts) >= 2:
        ticker = (parts[0] + random.choice(parts[1:])).upper() + random.choice(["X", "AI", "GO", "IN"])
    else:
        ticker = parts.upper() + random.choice(string.ascii_uppercase for _ in range(2))
    return ticker + random.choice(SUFFIXES)


def _gen_price() -> tuple[str, float]:
    """Generate random price and change%."""
    price_type = random.choice(["dust", "small", "medium", "big", "meme"])
    if price_type == "dust":
        price = f"0.{random.randint(1,9)}{'0'*random.randint(1,8)}{random.randint(1,9)}"
        price_num = float(f"0.{random.randint(1,99)}")
    elif price_type == "small":
        price_num = random.uniform(0.01, 1.0)
        price = f"${price_num:.4f}"
    elif price_type == "medium":
        price_num = random.uniform(1.0, 100.0)
        price = f"${price_num:.2f}"
    elif price_type == "big":
        price_num = random.uniform(100.0, 50000.0)
        price = f"${price_num:,.2f}"
    else:
        price_num = random.uniform(0.0001, 69.420)
        price = f"${price_num:.6f}"

    change = random.uniform(-80, 500)
    return price, change


def _gen_bread_price() -> tuple[str, float]:
    """Generate price in bread loaves."""
    bread = random.uniform(0.0001, 99999)
    if bread < 0.01:
        return f"0.{('0' * random.randint(1,6))}{random.randint(1,9)} хлеба", bread
    elif bread < 1:
        return f"{bread:.4f} хлеба", bread
    elif bread < 100:
        return f"{bread:.2f} хлеба", bread
    else:
        return f"{bread:,.1f} хлеба", bread


def _load_cfg() -> dict:
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": True}


def _save_cfg(cfg: dict) -> None:
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def register(client):
    import logging
    from datetime import datetime
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.crypto")

    async def _crypto_cmd(client, message: Message):
        parts = message.text.split()
        arg = parts[1] if len(parts) > 1 else ""

        cfg = _load_cfg()

        if arg == "off":
            cfg["enabled"] = False
            _save_cfg(cfg)
            await safe_edit(message, "🍞 Крипта выключена", parse_mode=ParseMode.HTML)
        elif arg == "on":
            cfg["enabled"] = True
            _save_cfg(cfg)
            await safe_edit(message, "🍞 Крипта включена", parse_mode=ParseMode.HTML)
        else:
            # Generate token
            name = _gen_name()
            ticker = _gen_ticker(name)
            price, change = _gen_price()
            bread_str, bread_val = _gen_bread_price()

            arrow = "📈" if change >= 0 else "📉"
            change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"

            # Market cap
            mcap = random.choice(["$0", "$42", "$1.337", "$69.420", f"${random.randint(1,999)}K",
                                  f"${random.randint(1,999)}M", f"${random.randint(1,99)}B", "∞"])

            comment = random.choice(COMMENTS)
            now = datetime.now().strftime("%H:%M")

            holders = random.randint(1, 999999)

            text = (
                f"🍞 <b>{name}</b> <code>{ticker}</code>\n\n"
                f"Цена: <b>{price}</b> {arrow} <code>{change_str}</code>\n"
                f"Курс к хлебу: <b>{bread_str}</b>\n"
                f"Market Cap: <code>{mcap}</code>\n"
                f"Holders: <code>{holders:,}</code>\n\n"
                f"<i>{comment}</i>\n"
                f"<i>Обновлено: {now} (каждые 5 сек) *</i>\n\n"
                f"<i>* не обновляется, мы врём</i>"
            )

            await safe_edit(message, text, parse_mode=ParseMode.HTML)

    client.add_handler(MessageHandler(
        _crypto_cmd,
        cmd("крипто"),
    ))


def on_load():
    print("[crypto] Loaded. -крипто")
