"""Тупые предсказания — каждые N сообщений юзербот пишет глупое предсказание."""

import os
import json
import random

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(SCRIPT_DIR, "settings.json")

# ── 30 тупых предсказаний ──
PREDICTIONS = [
    "сегодня тебя поздравит бот:) поздравляю тебя!",
    "сегодня ты найдёшь чужой носок под кроватью и осознаешь смысл жизни",
    "ближайшие 3 часа ты не потеряешь ключи. или потеряешь. кто я такой чтобы решать",
    "сегодня ты отправишь сообщение не в тот чат. классика",
    "кто-то прямо сейчас думает о тебе. скорее всего это я",
    "сегодня тебя ждёт удача. или нет. посмотрим кто первый устанет",
    "звёзды говорят: иди поспи, ты уже достаточно устал",
    "до конца дня тебе улыбнутся минимум 2 раза. или 1. или 0. предсказания это не точно",
    "сегодня подходящий день для грандиозных планов... которые ты не выполнишь",
    "твоё следующее сообщение будет начинаться с опечатки",
    "завтра будет лучше. а если нет — послезавтра. а если и тогда — ну такое",
    "сегодня вечером ты пожалеешь что не лёг спать раньше",
    "через 2 дня ты вспомнишь что забыл что-то сделать неделю назад",
    "бот предсказывает: ты сейчас читаешь это сообщение. в точку да?",
    "сегодня у тебя будет хорошее настроение. или плохое. 50/50",
    "до конца недели ты скажешь 'ещё 5 минутку' минимум 3 раза",
    "сегодня ты обнаружишь что ел что-то с просрочкой. уже ел. или только собираешься",
    "твой следующий скриншот будет случайным. ты know",
    "сегодня кто-то попросит у тебя одолжить. скажи нет. или да. мне всё равно",
    "у тебя скоро день рождения. или уже был. или через полгода. я слепой бот",
    "звёзды намекают: попей водички, ты же хотел",
    "сегодня тебе никто не напишет первым. нет, стоп, я же пишу",
    "предсказание: ты откроешь этот чат минимум ещё 5 раз сегодня",
    "через N часов ты поймёшь что забыл поесть. или уже переел",
    "сегодня тебе встретится кот. или собака. или голубь. животные повсюду",
    "бот настоятельно рекомендует: не делай того, о чём думаешь. или делай. рисковай",
    "сегодня ты потратишь деньги на что-то ненужное. и не пожалеешь",
    "предсказание: ты сейчас хочешь закатьть чат и заняться делами. не закрывай",
    "у тебя низкий заряд. поставь на зарядку. ты же не хочешь чтобы я исчез",
    "твоя следующая мысль: 'какой тупой бот'. угадал?",
]

_msg_counter = 0


def _load_cfg() -> dict:
    if os.path.exists(CFG_FILE):
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"n": 10, "enabled": True}


def _save_cfg(cfg: dict) -> None:
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def register(client):
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.predictions")

    async def _counter(client, message: Message):
        """Count every user message, trigger prediction every N."""
        global _msg_counter
        cfg = _load_cfg()

        if not cfg.get("enabled", True):
            return

        n = cfg.get("n", 10)
        if n <= 0:
            return

        _msg_counter += 1
        log.debug("pred counter: %d/%d", _msg_counter, n)

        if _msg_counter >= n:
            _msg_counter = 0
            pred = random.choice(PREDICTIONS)
            try:
                await message.reply_text(f"🔮 <i>{pred}</i>", parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                log.error("pred reply error: %s", e)

    async def _pred_cmd(client, message: Message):
        """Manage predictions: -pred | -pred N | -pred off | -pred on"""
        parts = message.text.split()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cfg = _load_cfg()

            # -pred (no arg) → status
            if not arg:
                n = cfg.get("n", 10)
                on = cfg.get("enabled", True)
                status = "включено" if on else "выключено"
                await safe_edit(message,
                    f"🔮 <b>Предсказания</b>\n\n"
                    f"Статус: {status}\n"
                    f"Каждые <b>{n}</b> сообщений\n\n"
                    f"<code>-pred N</code> — интервал (N сообщений)\n"
                    f"<code>-pred off</code> — выключить\n"
                    f"<code>-pred on</code> — включить",
                    parse_mode=ParseMode.HTML,
                )
                return

            # -pred off
            if arg == "off":
                cfg["enabled"] = False
                _save_cfg(cfg)
                await safe_edit(message, "🔮 Предсказания выключены", parse_mode=ParseMode.HTML)
                return

            # -pred on
            if arg == "on":
                cfg["enabled"] = True
                _save_cfg(cfg)
                await safe_edit(message, "🔮 Предсказания включены", parse_mode=ParseMode.HTML)
                return

            # -pred N → set interval
            try:
                n = int(arg)
            except ValueError:
                await safe_edit(message,
                    "❌ Укажи число. Пример: <code>-pred 5</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            if n < 1 or n > 999:
                await safe_edit(message, "❌ От 1 до 999", parse_mode=ParseMode.HTML)
                return

            cfg["n"] = n
            cfg["enabled"] = True
            _save_cfg(cfg)
            await safe_edit(message, f"🔮 Предсказания каждые {n} сообщений", parse_mode=ParseMode.HTML)

        except Exception as e:
            log.error("pred cmd error: %s", e, exc_info=True)

    # Counter — fires on ALL outgoing messages (from me)
    client.add_handler(MessageHandler(
        _counter,
        filters.outgoing & filters.me & ~filters.command(["pred"], prefixes="-"),
    ))

    # Command
    client.add_handler(MessageHandler(
        _pred_cmd,
        filters.command("pred", prefixes="-") & filters.me,
    ))


def on_load():
    print("[predictions] Loaded. -pred N / -pred off/on")
