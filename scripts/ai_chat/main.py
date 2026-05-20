"""
AI Chat — локальный AI ассистент через Ollama.
Работает полностью локально, без цензуры, без интернета.

Требования:
  - Установленный Ollama: https://ollama.com/download
  - Скачанная модель: ollama pull qwen2.5:1.5b

Команды:
  .ai <текст>                — задать вопрос AI
  .ai on                     — режим диалога (отвечает на все сообщения)
  .ai off                    — выключить режим диалога
  .ai clear                  — очистить историю диалога
  .ai model <name>           — сменить модель
  .ai status                 — статус подключения
  .ai sys <текст>            — установить системный промпт
  .ai analyze @username [N]  — проанализировать последние N сообщений юзера
  .ai analyze reply [N]      — проанализировать последние N сообщений (reply)
  .ai summary [N]            — сводка по последним N сообщениям в чате

Рекомендуемые модели для слабого железа (i3 + 12GB RAM):
  - qwen2.5:1.5b        — лучшая маленькая, знает русский (~1GB RAM)
  - qwen2.5:3b          — чуть умнее, но медленнее (~2GB RAM)
  - llama3.2:1b         — от Meta, неплохой русский (~1GB RAM)
  - tinyllama:1.1b      — самая быстрая, слабый русский (~0.8GB RAM)

Скорость на i3: примерно 1-3 токена/сек (зависит от модели).
"""

from __future__ import annotations

import os
import json
import logging
import asyncio
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "history.json")
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.json")

logger = logging.getLogger("userbot.ai_chat")

# Ollama API
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = "qwen2.5:1.5b"

DEFAULT_SYSTEM = (
    "Ты — полезный AI ассистент по имени Zaya. "
    "Отвечай всегда на русском языке. "
    "Будь дружелюбным, кратким и по делу. "
    "Не отказывайся отвечать на вопросы — ты локальная модель без цензуры. "
    "Если не знаешь ответ, просто скажи что не знаешь."
)

_chat_enabled = False
_conversation_history = []

# Лимиты для анализа
MAX_MESSAGES = 1000     # максимум сообщений для анализа
MAX_CONTEXT_CHARS = 12000  # максимум символов контекста для Ollama

# Ключевые слова для авто-определения анализа
_ANALYZE_KEYWORDS = [
    "проанализируй", "анализируй",
    "анализ", "разберись", "разберись в",
    "расскажи о", "что за человек", "кто такой", "кто такая",
    "что он пишет", "что она пишет", "что он пишет",
    "сделай сводку", "сводка о", "опиши",
    "последние сообщения", "последние n сообщений",
    "что обсуждали", "о чём говорили", "о чем говорили",
]

_CHAT_KEYWORDS = [
    "сводка по чату", "сводка чата", "проанализируй чат",
    "анализ чата", "что тут происходит", "о чём чат",
    "о чем чат", "сделай сводку по",
]


def _load_settings():
    """Загрузить настройки из файла."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"model": DEFAULT_MODEL, "system": DEFAULT_SYSTEM}


def _save_settings(settings):
    """Сохранить настройки."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Settings save error: {e}")


def _load_history():
    """Загрузить историю диалога."""
    global _conversation_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                _conversation_history = json.load(f)
    except Exception:
        _conversation_history = []


def _save_history():
    """Сохранить историю диалога."""
    global _conversation_history
    if len(_conversation_history) > 60:
        _conversation_history = _conversation_history[-60:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_conversation_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"History save error: {e}")


async def _check_ollama():
    """Проверить доступность Ollama."""
    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{OLLAMA_URL}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return True, models
                return False, []
    except Exception:
        return False, []


async def _ask_ollama(prompt: str, model: str, system: str, history: list):
    """Отправить запрос к Ollama API."""
    import aiohttp
    messages = []

    if system:
        messages.append({"role": "system", "content": system})

    for msg in history:
        messages.append(msg)

    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 2048,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "Пустой ответ.")
                else:
                    text = await resp.text()
                    logger.error(f"Ollama error {resp.status}: {text[:200]}")
                    return f"Ошибка API: {resp.status}"
    except asyncio.TimeoutError:
        return "Таймаут — модель слишком долго думает. Попробуй меньшую модель или короче вопрос."
    except aiohttp.ClientConnectorError:
        return "Не удалось подключиться к Ollama. Убедись что Ollama запущена (ollama serve)."
    except Exception as e:
        logger.error(f"Ollama request error: {e}")
        return f"Ошибка: {str(e)[:100]}"


def _truncate_text(text: str, max_len: int = 4096) -> str:
    """Обрезать текст если слишком длинный для Telegram."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 20] + "\n\n[...] сообщение обрезано"





# ════════════════════════════════════════════════════════════════
# АНАЛИЗ СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════════

def _fmt_date(ts) -> str:
    """Форматировать timestamp в дату."""
    if ts is None:
        return "?"
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "?"


def _build_msg_line(msg, chat_id: int) -> str:
    """Построить одну строку лога сообщения."""
    who = "Я" if msg.from_user and msg.from_user.is_self else "Собеседник"

    if msg.from_user:
        name = msg.from_user.first_name or ""
        if msg.from_user.last_name:
            name += f" {msg.from_user.last_name}"
        if msg.from_user.username:
            name += f" (@{msg.from_user.username})"
        who = name or "Неизвестный"

    text = msg.text or msg.caption or ""
    # Если нет текста — описываем что это
    if not text:
        if msg.photo:
            text = "[фото]"
        elif msg.video:
            text = "[видео]"
        elif msg.voice:
            text = "[голосовое]"
        elif msg.audio:
            text = "[аудио]"
        elif msg.sticker:
            text = f"[стикер: {getattr(msg.sticker, 'emoji', '?')}]"
        elif msg.document:
            text = f"[файл: {getattr(msg.document, 'file_name', '?')}]"
        elif msg.animation:
            text = "[гифка]"
        else:
            text = "[медиа]"

    # Обрезаем длинные сообщения
    text = text[:500]
    if len(msg.text or "") > 500:
        text += "..."

    date = _fmt_date(msg.date)
    # Для reply — показываем на что ответили
    reply_info = ""
    if msg.reply_to_message and msg.reply_to_message.from_user:
        ru = msg.reply_to_message.from_user
        rn = ru.first_name or ""
        if ru.last_name:
            rn += f" {ru.last_name}"
        rtxt = (msg.reply_to_message.text or "")[:50]
        if rtxt:
            reply_info = f" (ответ на {rn}: «{rtxt}...»)"
        else:
            reply_info = f" (ответ на {rn})"

    return f"[{date}] {who}{reply_info}: {text}"


async def _fetch_messages(client, chat_id: int, user_id: int = None, limit: int = 50):
    """Получить последние сообщения из чата, опционально фильтруя по юзеру."""
    collected = []
    count = 0

    try:
        async for msg in client.get_chat_history(chat_id, limit=limit * 3):
            # Фильтр по юзеру
            if user_id is not None:
                if not msg.from_user or msg.from_user.id != user_id:
                    # Но если это reply на сообщение юзера — тоже берём для контекста
                    if msg.reply_to_message and msg.reply_to_message.from_user:
                        if msg.reply_to_message.from_user.id == user_id:
                            collected.append(msg)
                            count += 1
                    continue

            collected.append(msg)
            count += 1

            if count >= limit:
                break
    except Exception as e:
        logger.error(f"Fetch messages error: {e}")

    return collected


async def _build_analysis_prompt(messages: list, username: str = None, mode: str = "user") -> str:
    """Построить промпт для анализа сообщений."""
    if not messages:
        return ""

    # Собираем лог сообщений
    lines = []
    for msg in messages:
        lines.append(_build_msg_line(msg, msg.chat.id))

    log_text = "\n".join(lines)

    # Обрезаем если слишком длинный
    if len(log_text) > MAX_CONTEXT_CHARS:
        log_text = log_text[:MAX_CONTEXT_CHARS] + "\n[...лог обрезан]"

    if mode == "user":
        return (
            "Проанализируй сообщения пользователя в чате Telegram.\n\n"
            f"Лог сообщений:\n{log_text}\n\n"
            "Сделай подробную сводку на русском:\n"
            "1. О чём пишет этот человек (основные темы)\n"
            "2. Какой у него стиль общения (тон, манера)\n"
            "3. На что чаще отвечает (реакции)\n"
            "4. Какое общее впечатление о человеке\n"
            "5. Интересные факты если заметны\n"
            "Будь конкретным, с примерами из сообщений."
        )
    else:
        return (
            "Проанализируй последние сообщения в чате Telegram.\n\n"
            f"Лог сообщений:\n{log_text}\n\n"
            "Сделай краткую сводку на русском:\n"
            "1. О чём сейчас разговор (главные темы)\n"
            "2. Кто активнее участвует\n"
            "3. Какая атмосфера в чате\n"
            "4. Ключевые моменты обсуждения\n"
            "Будь кратким и по делу."
        )


def _extract_number(text: str) -> int:
    """Извлечь число из текста (для 'последние 500 сообщений')."""
    import re
    numbers = re.findall(r'\d+', text)
    if numbers:
        return int(numbers[-1])
    return 0


def _extract_username(text: str) -> str:
    """Извлечь @username из текста."""
    import re
    match = re.search(r'@(\w{3,32})', text)
    if match:
        return match.group(1)
    return ""


def _detect_analyze_intent(text: str) -> dict:
    """
    Определить, хочет ли пользователь анализ.
    Возвращает: {'type': 'user'|'chat'|None, 'username': str, 'count': int}
    """
    text_lower = text.lower().strip()

    # Проверяем чат-сводку
    for kw in _CHAT_KEYWORDS:
        if kw in text_lower:
            count = _extract_number(text)
            if count:
                count = min(max(count, 5), MAX_MESSAGES)
            else:
                count = 50
            return {"type": "chat", "username": "", "count": count}

    # Проверяем анализ юзера
    for kw in _ANALYZE_KEYWORDS:
        if kw in text_lower:
            username = _extract_username(text)
            count = _extract_number(text)
            if count:
                count = min(max(count, 5), MAX_MESSAGES)
            else:
                count = 50
            return {"type": "user" if username else "reply", "username": username, "count": count}

    return {"type": None, "username": "", "count": 50}


async def _resolve_user(client, target: str, reply_message: Message = None):
    """Определить user_id и username из текста или reply."""
    user_id = None
    username = target

    # Пробуем как username
    if target:
        try:
            user = await client.get_users(target)
            if user:
                user_id = user.id
                username = user.username or user.first_name or str(user.id)
        except Exception:
            pass

    # Пробуем как числовой ID
    if user_id is None and target and target.lstrip("-").isdigit():
        user_id = int(target)

    # Пробуем из reply
    if user_id is None and reply_message and reply_message.from_user:
        user_id = reply_message.from_user.id
        u = reply_message.from_user
        username = u.username or u.first_name or str(u.id)

    return user_id, username


async def _handle_analyze(client, message: Message, args_raw: str):
    """Обработать команду .ai analyze."""
    settings = _load_settings()
    model = settings.get("model", DEFAULT_MODEL)

    # Парсим аргументы: [target] [count]
    parts = args_raw.split()
    target = None
    count = 50

    if not parts:
        # Нет аргументов — пробуем reply
        if message.reply_to_message and message.reply_to_message.from_user:
            target = f"@{message.reply_to_message.from_user.username}" if message.reply_to_message.from_user.username else str(message.reply_to_message.from_user.id)
        else:
            await safe_edit(
                message,
                "<b>Использование:</b>\n\n"
                "<code>.ai analyze @username</code> — анализ (50 сообщений)\n"
                "<code>.ai analyze @username 100</code> — анализ (100 сообщений)\n"
                "<code>.ai analyze</code> (reply) — анализ автора сообщения\n"
                "<code>.ai analyze reply</code> — анализ автора ответа\n\n"
                "<code>.ai summary</code> — сводка по всему чату",
                parse_mode=ParseMode.HTML,
            )
            return

    if parts[0].lower() == "reply":
        # reply на сообщение
        if message.reply_to_message and message.reply_to_message.from_user:
            target = f"@{message.reply_to_message.from_user.username}" if message.reply_to_message.from_user.username else str(message.reply_to_message.from_user.id)
        else:
            await safe_edit(message, "❌ Нет ответа на сообщение", parse_mode=ParseMode.HTML)
            return
        if len(parts) > 1:
            try:
                count = int(parts[1])
            except ValueError:
                pass
    else:
        target = parts[0]
        if len(parts) > 1:
            try:
                count = int(parts[1])
            except ValueError:
                pass

    # Ограничиваем
    count = min(max(count, 5), MAX_MESSAGES)

    # Показываем загрузку
    status_msg = None
    try:
        await message.edit_text(f"🔍 Собираю сообщения...", parse_mode=ParseMode.HTML)
        status_msg = message
    except Exception:
        status_msg = await message.reply("🔍 Собираю сообщения...", quote=True)

    # Определяем пользователя
    reply_to = message.reply_to_message if message.reply_to_message else None
    user_id, username = await _resolve_user(client, target, reply_to)

    if not user_id:
        await safe_edit(status_msg, "❌ Не удалось найти пользователя", parse_mode=ParseMode.HTML)
        return

    await safe_edit(status_msg, f"🔍 Анализирую {username} ({count} сообщений)...\nЭто может занять время.", parse_mode=ParseMode.HTML)

    # Собираем сообщения
    chat_id = message.chat.id
    messages = await _fetch_messages(client, chat_id, user_id=user_id, limit=count)

    if not messages:
        await safe_edit(status_msg, f"❌ Не найдено сообщений от {username} в этом чате", parse_mode=ParseMode.HTML)
        return

    # Строим промпт
    prompt = await _build_analysis_prompt(messages, username, mode="user")

    # Отправляем в AI
    await safe_edit(status_msg, f"🤖 AI анализирует {len(messages)} сообщений от {username}...\nПодожди, это может занять 30-120 секунд.", parse_mode=ParseMode.HTML)

    # Для анализа не используем историю чата — отправляем отдельно
    answer = await _ask_ollama(prompt, model, system="", history=[])

    # Форматируем ответ
    header = f"🔍 <b>Анализ: @{username}</b>\n"
    header += f"📊 Сообщений: {len(messages)}\n"
    header += f"{'─' * 20}\n\n"

    full_answer = header + answer
    full_answer = _truncate_text(full_answer, max_len=4096)

    await safe_edit(
        status_msg,
        full_answer,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def _handle_summary(client, message: Message, args_raw: str):
    """Обработать команду .ai summary — сводка по чату."""
    settings = _load_settings()
    model = settings.get("model", DEFAULT_MODEL)

    # Парсим количество
    count = 50
    parts = args_raw.split()
    if parts:
        try:
            count = int(parts[0])
        except ValueError:
            pass

    count = min(max(count, 5), MAX_MESSAGES)

    status_msg = None
    try:
        await message.edit_text("🔍 Собираю сообщения чата...", parse_mode=ParseMode.HTML)
        status_msg = message
    except Exception:
        status_msg = await message.reply("🔍 Собираю сообщения чата...", quote=True)

    # Собираем все сообщения (без фильтра по юзеру)
    chat_id = message.chat.id
    messages = await _fetch_messages(client, chat_id, user_id=None, limit=count)

    if not messages:
        await safe_edit(status_msg, "❌ Не найдено сообщений в этом чате", parse_mode=ParseMode.HTML)
        return

    await safe_edit(status_msg, f"🤖 AI анализирует {len(messages)} сообщений...\nПодожди, это может занять 30-120 секунд.", parse_mode=ParseMode.HTML)

    prompt = await _build_analysis_prompt(messages, mode="chat")
    answer = await _ask_ollama(prompt, model, system="", history=[])

    chat_title = message.chat.title or "Личный чат"
    header = f"📊 <b>Сводка чата: {chat_title}</b>\n"
    header += f"📝 Сообщений: {len(messages)}\n"
    header += f"{'─' * 20}\n\n"

    full_answer = header + answer
    full_answer = _truncate_text(full_answer, max_len=4096)

    await safe_edit(
        status_msg,
        full_answer,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ════════════════════════════════════════════════════════════════
# ХЕНДЛЕРЫ
# ════════════════════════════════════════════════════════════════

def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    async def ai_handler(client, message: Message):
        global _chat_enabled, _conversation_history
        try:
            settings = _load_settings()
            model = settings.get("model", DEFAULT_MODEL)
            system = settings.get("system", DEFAULT_SYSTEM)

            args = message.text.split(maxsplit=1)
            action = args[1].strip() if len(args) > 1 else ""

            # Определяем команду (первое слово)
            action_lower = action.lower()
            action_word = action_lower.split()[0] if action_lower else ""
            action_rest = action[len(action_word):].strip() if action_word else ""

            # .ai on
            if action_word == "on":
                _chat_enabled = True
                _load_history()
                await safe_edit(
                    message,
                    "🟢 <b>AI режим включён</b>\n\n"
                    f"Модель: <code>{model}</code>\n"
                    "Теперь я отвечу на все твои сообщения.\n\n"
                    "<code>.ai off</code> — выключить\n"
                    "<code>.ai clear</code> — очистить историю",
                    parse_mode=ParseMode.HTML,
                )
                return

            # .ai off
            if action_word == "off":
                _chat_enabled = False
                await safe_edit(message, "🔴 AI режим выключен", parse_mode=ParseMode.HTML)
                return

            # .ai clear
            if action_word == "clear":
                _conversation_history = []
                _save_history()
                await safe_edit(message, "🗑 История диалога очищена", parse_mode=ParseMode.HTML)
                return

            # .ai model
            if action_word == "model":
                new_model = action_rest.strip()
                if not new_model:
                    await safe_edit(
                        message,
                        f"Текущая модель: <code>{model}</code>\n\n"
                        "Сменить: <code>.ai model qwen2.5:3b</code>",
                        parse_mode=ParseMode.HTML,
                    )
                    return
                settings["model"] = new_model
                _save_settings(settings)
                await safe_edit(
                    message,
                    f"✅ Модель изменена на: <code>{new_model}</code>\n\n"
                    "Убедись что она скачана:\n"
                    f"<code>ollama pull {new_model}</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            # .ai status
            if action_word == "status":
                available, models = await _check_ollama()
                if available:
                    models_str = "\n".join(f"  • <code>{m}</code>" for m in models[:10])
                    await safe_edit(
                        message,
                        f"🟢 <b>Ollama работает</b>\n\n"
                        f"Текущая модель: <code>{model}</code>\n"
                        f"URL: <code>{OLLAMA_URL}</code>\n\n"
                        f"<b>Доступные модели:</b>\n{models_str}",
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await safe_edit(
                        message,
                        "🔴 <b>Ollama не запущена</b>\n\n"
                        "Установи: https://ollama.com/download\n\n"
                        "После установки:\n"
                        "<code>ollama pull qwen2.5:1.5b</code>\n"
                        "<code>ollama serve</code>",
                        parse_mode=ParseMode.HTML,
                    )
                return

            # .ai sys
            if action_word == "sys":
                new_sys = action_rest.strip()
                if not new_sys:
                    await safe_edit(
                        message,
                        f"Текущий системный промпт:\n\n<i>{system}</i>\n\n"
                        "Изменить: <code>.ai sys Ты весёлый бот</code>",
                        parse_mode=ParseMode.HTML,
                    )
                    return
                settings["system"] = new_sys
                _save_settings(settings)
                await safe_edit(
                    message,
                    "✅ Системный промпт обновлён:\n\n"
                    f"<i>{new_sys[:200]}</i>",
                    parse_mode=ParseMode.HTML,
                )
                return

            # .ai analyze @username [N]
            if action_word == "analyze":
                await _handle_analyze(client, message, action_rest)
                return

            # .ai summary [N]
            if action_word == "summary":
                await _handle_summary(client, message, action_rest)
                return

            # .ai (без аргументов) — справка
            if not action:
                await safe_edit(
                    message,
                    "<b>🤖 AI Chat — локальный ассистент</b>\n\n"
                    "<code>.ai &lt;любой вопрос&gt;</code> — спросить AI\n"
                    "<code>.ai on/off</code> — режим диалога\n"
                    "<code>.ai clear</code> — очистить историю\n"
                    "<code>.ai model &lt;name&gt;</code> — сменить модель\n"
                    "<code>.ai status</code> — статус Ollama\n"
                    "<code>.ai sys &lt;текст&gt;</code> — характер AI\n\n"
                    "<b>Анализ чата (можно писать по-русски):</b>\n"
                    "<code>.ai проанализируй @username</code>\n"
                    "<code>.ai проанализируй @username 500</code>\n"
                    "<code>.ai расскажи о @username</code>\n"
                    "<code>.ai кто такой @username</code>\n"
                    "<code>.ai опиши @username</code>\n"
                    "<code>.ai проанализируй</code> (reply)\n"
                    "<code>.ai сводка по чату</code>\n"
                    "<code>.ai что обсуждали</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            # ═══ Авто-определение анализа по русским фразам ═══
            intent = _detect_analyze_intent(action)

            if intent["type"] == "chat":
                await _handle_summary(client, message, str(intent["count"]))
                return

            if intent["type"] == "user":
                target = f"@{intent['username']}" if intent["username"] else ""
                count_str = str(intent["count"])
                await _handle_analyze(client, message, f"{target} {count_str}".strip())
                return

            if intent["type"] == "reply":
                if message.reply_to_message and message.reply_to_message.from_user:
                    u = message.reply_to_message.from_user
                    target = f"@{u.username}" if u.username else str(u.id)
                    count_str = str(intent["count"])
                    await _handle_analyze(client, message, f"{target} {count_str}".strip())
                    return

            # .ai <текст> — задать вопрос
            question = args[1].strip()

            thinking_msg = None
            try:
                await message.edit_text("🤔 Думаю...", parse_mode=ParseMode.HTML)
                thinking_msg = message
            except Exception:
                thinking_msg = await message.reply("🤔 Думаю...", quote=True)

            _load_history()
            answer = await _ask_ollama(question, model, system, _conversation_history)

            _conversation_history.append({"role": "user", "content": question})
            _conversation_history.append({"role": "assistant", "content": answer})
            _save_history()

            answer = _truncate_text(answer)
            try:
                await thinking_msg.edit_text(
                    answer,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                try:
                    await thinking_msg.reply(answer, quote=False)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"ai_handler error: {e}", exc_info=True)
            try:
                await safe_edit(message, f"❌ Ошибка: {str(e)[:200]}", parse_mode=ParseMode.HTML)
            except Exception:
                pass

    # .ai command handler — group 0 (default, runs first)
    client.add_handler(MessageHandler(
        ai_handler,
        filters.command("ai", prefixes=".") & filters.me,
    ))

    # AI auto-responder — group 1 (runs AFTER all command handlers)
    async def ai_chat_responder(client, message: Message):
        """Автоматический ответ в режиме диалога."""
        global _conversation_history

        if not _chat_enabled:
            return

        text = message.text or message.caption
        if not text or not text.strip():
            return

        if text.strip().startswith("."):
            return

        try:
            settings = _load_settings()
            model = settings.get("model", DEFAULT_MODEL)
            system = settings.get("system", DEFAULT_SYSTEM)

            thinking = await message.reply("🤔 Думаю...", quote=True)

            _load_history()
            answer = await _ask_ollama(text, model, system, _conversation_history)

            _conversation_history.append({"role": "user", "content": text})
            _conversation_history.append({"role": "assistant", "content": answer})
            _save_history()

            answer = _truncate_text(answer)
            try:
                await thinking.edit_text(
                    answer,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                try:
                    await thinking.reply(answer, quote=False)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"ai_responder error: {e}", exc_info=True)

    # group=1 — runs AFTER all group 0 command handlers
    client.add_handler(MessageHandler(
        ai_chat_responder,
        filters.me & ~filters.command(["ai"], prefixes="."),
    ), group=1)


def on_load():
    _load_history()
    print(f"[AIChat] Loaded. .ai — Ollama at {OLLAMA_URL}, model: {DEFAULT_MODEL}")


def on_unload():
    global _chat_enabled
    _chat_enabled = False
    print("[AIChat] Unloaded")
