"""
AI Chat — AI ассистент с поддержкой Ollama и API (DeepSeek, OpenAI и совместимые).

Провайдеры:
  - ollama: локально, без цензуры
  - api: DeepSeek / OpenAI / любой совместимый

Контекст: отдельная история диалога для каждого чата.

Команды:
  -ии <текст>                — задать вопрос AI
  -ии вкл / выкл             — режим диалога (отвечает на ваши сообщения)
  -ии агент вкл / выкл       — агент-режим (отвечает на все сообщения в чате)
  -ии оч                     — очистить историю текущего чата
  -ии провайдер [ollama/api] — сменить провайдера
  -ии ключ sk-...            — установить API ключ
  -ии урл https://...        — установить API URL
  -ии мод <name>             — сменить модель
  -ии ст                     — статус подключения
  -ии сис <текст>            — системный промпт
  -ии ан @username [N]       — анализ сообщений
  -ии св [N]                 — сводка по чату
"""

from __future__ import annotations

import os
import json
import logging
import asyncio
import tempfile
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.json")
HISTORY_DIR = os.path.join(SCRIPT_DIR, "history")

logger = logging.getLogger("sandusr.ai_chat")

# ── Defaults ────────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

DEFAULT_SYSTEM = (
    "Ты — полезный AI ассистент по имени Zaya. "
    "Отвечай всегда на русском языке. "
    "Будь дружелюбным, кратким и по делу."
)

# Расширения текстовых файлов для агент-режима
_TEXT_EXTENSIONS = (
    ".txt", ".py", ".js", ".ts", ".json", ".md", ".csv", ".html", ".css",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".sh",
    ".bat", ".c", ".cpp", ".h", ".hpp", ".java", ".rb", ".go", ".rs",
    ".sql", ".env", ".dockerfile", ".makefile", ".gitignore",
    ".jsx", ".tsx", ".vue", ".svelte", ".php", ".swift", ".kt",
    ".lua", ".r", ".pl", ".ps1", ".zsh", ".bash", ".fish",
    ".proto", ".graphql", ".tf", ".hcl",
)

# Лимиты
MAX_MESSAGES = 1000
MAX_CONTEXT_CHARS = 12000
MAX_FILE_CHARS = 15000
HISTORY_LIMIT = 80
AGENT_COOLDOWN = 5  # секунд между ответами агента

# ── State ───────────────────────────────────────────────────────

_chat_enabled = False        # авто-ответ на свои сообщения
_agent_chats: set = set()    # chat_id где агент активен
_last_agent_reply: dict = {} # chat_id → timestamp последнего ответа


# ════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ════════════════════════════════════════════════════════════════

def _load_settings() -> dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "provider": "ollama",
        "api_base": "https://api.deepseek.com",
        "api_key": "",
        "model": "qwen2.5:1.5b",
        "system": DEFAULT_SYSTEM,
        "agent_chats": [],
    }


def _save_settings(s: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Settings save error: {e}")


# ════════════════════════════════════════════════════════════════
#  ИСТОРИЯ (на чат)
# ════════════════════════════════════════════════════════════════

def _history_path(chat_id) -> str:
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")


def _load_history(chat_id) -> list:
    fp = _history_path(chat_id)
    try:
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_history(chat_id, history: list):
    if len(history) > HISTORY_LIMIT:
        history = history[-HISTORY_LIMIT:]
    fp = _history_path(chat_id)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"History save error: {e}")


# ════════════════════════════════════════════════════════════════
#  AI ЗАПРОСЫ
# ════════════════════════════════════════════════════════════════

async def _ask_ollama(prompt: str, model: str, system: str, history: list) -> str:
    """Запрос к локальной Ollama."""
    import aiohttp

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 2048},
    }

    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{OLLAMA_URL}/api/chat", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "Пустой ответ.")
                text = await resp.text()
                logger.error(f"Ollama error {resp.status}: {text[:200]}")
                return f"Ошибка API: {resp.status}"
    except asyncio.TimeoutError:
        return "Таймаут — модель слишком долго думает."
    except aiohttp.ClientConnectorError:
        return "Не удалось подключиться к Ollama. Убедись что она запущена."
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return f"Ошибка: {str(e)[:100]}"


async def _ask_api(prompt: str, model: str, system: str, history: list,
                   api_base: str, api_key: str) -> str:
    """Запрос к API (OpenAI / DeepSeek совместимый)."""
    import aiohttp

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"

    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "Пустой ответ.")
                    return "Пустой ответ от API."
                text = await resp.text()
                logger.error(f"API error {resp.status}: {text[:300]}")
                return f"Ошибка API: {resp.status}"
    except asyncio.TimeoutError:
        return "Таймаут — API слишком долго отвечает."
    except aiohttp.ClientConnectorError:
        return f"Не удалось подключиться к {api_base}"
    except Exception as e:
        logger.error(f"API error: {e}")
        return f"Ошибка: {str(e)[:100]}"


async def _ask_ai(prompt: str, settings: dict, history: list) -> str:
    """Универсальный запрос — маршрутизирует по провайдеру."""
    provider = settings.get("provider", "ollama")
    model = settings.get("model", "qwen2.5:1.5b")
    system = settings.get("system", DEFAULT_SYSTEM)

    if provider == "api":
        api_key = settings.get("api_key", "")
        api_base = settings.get("api_base", "https://api.deepseek.com")
        if not api_key:
            return "API ключ не установлен. Установи: <code>-ии ключ sk-...</code>"
        return await _ask_api(prompt, model, system, history, api_base, api_key)
    else:
        return await _ask_ollama(prompt, model, system, history)


async def _check_ollama():
    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{OLLAMA_URL}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return True, [m.get("name", "") for m in data.get("models", [])]
                return False, []
    except Exception:
        return False, []


async def _check_api(api_base: str, api_key: str):
    """Проверить доступность API."""
    import aiohttp
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/models"
    else:
        url = base + "/v1/models"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("id", "") for m in data.get("data", [])]
                    return True, models
                return False, []
    except Exception:
        return False, []


def _truncate_text(text: str, max_len: int = 4096) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 20] + "\n\n[...] сообщение обрезано"


# ════════════════════════════════════════════════════════════════
#  ФАЙЛЫ (для агент-режима)
# ════════════════════════════════════════════════════════════════

def _is_text_file(message) -> bool:
    """Проверить, содержит ли сообщение текстовый файл."""
    if not message.document:
        return False
    mime = (message.document.mime_type or "").lower()
    fname = (message.document.file_name or "").lower()
    if mime.startswith("text/"):
        return True
    return any(fname.endswith(ext) for ext in _TEXT_EXTENSIONS)


async def _extract_file_content(message) -> tuple:
    """Скачать файл и извлечь текст. Возвращает (filename, text) или None."""
    if not _is_text_file(message):
        return None

    fname = message.document.file_name or "file"
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(fname)[1])
        tmp_path = tmp.name
        tmp.close()

        await message.download(file_name=tmp_path)

        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(MAX_FILE_CHARS)

        os.unlink(tmp_path)
        return fname, text
    except Exception as e:
        logger.error(f"File extract error: {e}")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    return None


# ════════════════════════════════════════════════════════════════
#  АНАЛИЗ СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════════

_ANALYZE_KEYWORDS = [
    "проанализируй", "анализируй", "анализ", "разберись",
    "расскажи о", "что за человек", "кто такой", "кто такая",
    "что он пишет", "что она пишет",
    "сделай сводку", "сводка о", "опиши",
    "последние сообщения", "что обсуждали", "о чём говорили",
]

_CHAT_KEYWORDS = [
    "сводка по чату", "сводка чата", "проанализируй чат",
    "анализ чата", "что тут происходит", "о чём чат",
    "сделай сводку по",
]


def _fmt_date(ts) -> str:
    if ts is None:
        return "?"
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "?"


def _build_msg_line(msg, chat_id: int) -> str:
    who = "Я"
    if msg.from_user:
        name = msg.from_user.first_name or ""
        if msg.from_user.last_name:
            name += f" {msg.from_user.last_name}"
        if msg.from_user.username:
            name += f" (@{msg.from_user.username})"
        who = name or "Неизвестный"

    text = msg.text or msg.caption or ""
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

    text = text[:500]

    reply_info = ""
    if msg.reply_to_message and msg.reply_to_message.from_user:
        ru = msg.reply_to_message.from_user
        rn = ru.first_name or ""
        if ru.last_name:
            rn += f" {ru.last_name}"
        rtxt = (msg.reply_to_message.text or "")[:50]
        reply_info = f" (ответ на {rn}: «{rtxt}...»)" if rtxt else f" (ответ на {rn})"

    return f"[{_fmt_date(msg.date)}] {who}{reply_info}: {text}"


async def _fetch_messages(client, chat_id: int, user_id=None, limit=50):
    collected = []
    count = 0
    try:
        async for msg in client.get_chat_history(chat_id, limit=limit * 3):
            if user_id is not None:
                if not msg.from_user or msg.from_user.id != user_id:
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


async def _build_analysis_prompt(messages, username=None, mode="user"):
    if not messages:
        return ""
    lines = [_build_msg_line(msg, msg.chat.id) for msg in messages]
    log_text = "\n".join(lines)
    if len(log_text) > MAX_CONTEXT_CHARS:
        log_text = log_text[:MAX_CONTEXT_CHARS] + "\n[...обрезано]"

    if mode == "user":
        return (
            "Проанализируй сообщения пользователя в чате Telegram.\n\n"
            f"Лог:\n{log_text}\n\n"
            "Сделай подробную сводку на русском:\n"
            "1. О чём пишет (темы)\n"
            "2. Стиль общения\n"
            "3. На что чаще отвечает\n"
            "4. Общее впечатление\n"
            "5. Интересные факты\n"
            "Будь конкретным, с примерами."
        )
    else:
        return (
            "Проанализируй последние сообщения в чате Telegram.\n\n"
            f"Лог:\n{log_text}\n\n"
            "Сделай краткую сводку на русском:\n"
            "1. О чём разговор\n"
            "2. Кто активнее\n"
            "3. Атмосфера\n"
            "4. Ключевые моменты\n"
            "Будь кратким."
        )


def _extract_number(text: str) -> int:
    import re
    nums = re.findall(r'\d+', text)
    return int(nums[-1]) if nums else 0


def _extract_username(text: str) -> str:
    import re
    m = re.search(r'@(\w{3,32})', text)
    return m.group(1) if m else ""


def _detect_analyze_intent(text: str) -> dict:
    t = text.lower().strip()
    for kw in _CHAT_KEYWORDS:
        if kw in t:
            count = _extract_number(text) or 50
            return {"type": "chat", "username": "", "count": min(max(count, 5), MAX_MESSAGES)}
    for kw in _ANALYZE_KEYWORDS:
        if kw in t:
            username = _extract_username(text)
            count = _extract_number(text) or 50
            count = min(max(count, 5), MAX_MESSAGES)
            return {"type": "user" if username else "reply", "username": username, "count": count}
    return {"type": None, "username": "", "count": 50}


async def _resolve_user(client, target, reply_message=None):
    user_id = None
    username = target
    if target:
        try:
            user = await client.get_users(target)
            if user:
                user_id = user.id
                username = user.username or user.first_name or str(user.id)
        except Exception:
            pass
    if user_id is None and target and target.lstrip("-").isdigit():
        user_id = int(target)
    if user_id is None and reply_message and reply_message.from_user:
        user_id = reply_message.from_user.id
        u = reply_message.from_user
        username = u.username or u.first_name or str(u.id)
    return user_id, username


async def _handle_analyze(client, message, args_raw):
    settings = _load_settings()
    chat_id = message.chat.id
    history = _load_history(chat_id)

    parts = args_raw.split()
    target = None
    count = 50

    if not parts:
        if message.reply_to_message and message.reply_to_message.from_user:
            u = message.reply_to_message.from_user
            target = f"@{u.username}" if u.username else str(u.id)
        else:
            await safe_edit(message,
                "<b>Использование:</b>\n\n"
                "<code>-ии ан @username</code> — анализ (50)\n"
                "<code>-ии ан @username 100</code> — анализ (100)\n"
                "<code>-ии ан</code> (ответ) — анализ автора\n"
                "<code>-ии св</code> — сводка по чату",
                parse_mode=ParseMode.HTML)
            return

    if parts[0].lower() == "reply":
        if message.reply_to_message and message.reply_to_message.from_user:
            u = message.reply_to_message.from_user
            target = f"@{u.username}" if u.username else str(u.id)
        else:
            await safe_edit(message, "❌ Нет ответа на сообщение", parse_mode=ParseMode.HTML)
            return
        if len(parts) > 1:
            try: count = int(parts[1])
            except ValueError: pass
    else:
        target = parts[0]
        if len(parts) > 1:
            try: count = int(parts[1])
            except ValueError: pass

    count = min(max(count, 5), MAX_MESSAGES)

    status_msg = await safe_edit(message, "🔍 Собираю сообщения...", parse_mode=ParseMode.HTML)
    if not status_msg:
        status_msg = await message.reply("🔍 Собираю сообщения...", quote=True)

    reply_to = message.reply_to_message
    user_id, username = await _resolve_user(client, target, reply_to)
    if not user_id:
        await safe_edit(status_msg, "❌ Не удалось найти пользователя", parse_mode=ParseMode.HTML)
        return

    await safe_edit(status_msg, f"🔍 Анализирую {username} ({count} сообщений)...", parse_mode=ParseMode.HTML)

    messages = await _fetch_messages(client, chat_id, user_id=user_id, limit=count)
    if not messages:
        await safe_edit(status_msg, f"❌ Не найдено сообщений от {username}", parse_mode=ParseMode.HTML)
        return

    prompt = await _build_analysis_prompt(messages, username, mode="user")
    await safe_edit(status_msg, f"🤖 AI анализирует {len(messages)} сообщений...", parse_mode=ParseMode.HTML)

    answer = await _ask_ai(prompt, settings, [])

    header = f"🔍 <b>Анализ: @{username}</b>\n📊 Сообщений: {len(messages)}\n{'─' * 20}\n\n"
    await safe_edit(status_msg, _truncate_text(header + answer), parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True)


async def _handle_summary(client, message, args_raw):
    settings = _load_settings()
    count = 50
    parts = args_raw.split()
    if parts:
        try: count = int(parts[0])
        except ValueError: pass
    count = min(max(count, 5), MAX_MESSAGES)

    chat_id = message.chat.id
    status_msg = await safe_edit(message, "🔍 Собираю сообщения чата...", parse_mode=ParseMode.HTML)
    if not status_msg:
        status_msg = await message.reply("🔍 Собираю сообщения чата...", quote=True)

    messages = await _fetch_messages(client, chat_id, user_id=None, limit=count)
    if not messages:
        await safe_edit(status_msg, "❌ Не найдено сообщений", parse_mode=ParseMode.HTML)
        return

    await safe_edit(status_msg, f"🤖 AI анализирует {len(messages)} сообщений...", parse_mode=ParseMode.HTML)
    prompt = await _build_analysis_prompt(messages, mode="chat")
    answer = await _ask_ai(prompt, settings, [])

    chat_title = message.chat.title or "Личный чат"
    header = f"📊 <b>Сводка: {chat_title}</b>\n📝 Сообщений: {len(messages)}\n{'─' * 20}\n\n"
    await safe_edit(status_msg, _truncate_text(header + answer), parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True)


# ════════════════════════════════════════════════════════════════
#  ХЕНДЛЕРЫ
# ════════════════════════════════════════════════════════════════

def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from pyrogram.enums import ParseMode
    from scripts._utils import cmd, cmd_neg, safe_edit

    global _agent_chats
    s = _load_settings()
    _agent_chats = set(s.get("agent_chats", []))

    # ── -ии command ─────────────────────────────────────────────
    async def ai_handler(client, message: Message):
        global _chat_enabled
        try:
            settings = _load_settings()
            provider = settings.get("provider", "ollama")

            args = message.text.split(maxsplit=1)
            action = args[1].strip() if len(args) > 1 else ""
            action_lower = action.lower()
            action_word = action_lower.split()[0] if action_lower else ""
            action_rest = action[len(action_word):].strip() if action_word else ""

            chat_id = message.chat.id

            # ── вкл ─────────────────────────────────────────────
            if action_word in ("вкл", "он", "on"):
                _chat_enabled = True
                await safe_edit(message,
                    f"🟢 <b>AI режим включён</b>\n\n"
                    f"Провайдер: <code>{provider}</code>\n"
                    f"Модель: <code>{settings.get('model', '')}</code>\n"
                    "Отвечаю на все твои сообщения.\n\n"
                    "<code>-ии выкл</code> — выключить\n"
                    "<code>-ии оч</code> — очистить историю",
                    parse_mode=ParseMode.HTML)
                return

            # ── выкл ────────────────────────────────────────────
            if action_word in ("выкл", "офф", "off"):
                _chat_enabled = False
                await safe_edit(message, "🔴 AI режим выключен", parse_mode=ParseMode.HTML)
                return

            # ── агент ───────────────────────────────────────────
            if action_word in ("агент", "agent", "аг"):
                sub = action_rest.split()[0].lower() if action_rest else ""

                if sub in ("вкл", "он", "on"):
                    _agent_chats.add(chat_id)
                    settings["agent_chats"] = list(_agent_chats)
                    _save_settings(settings)
                    await safe_edit(message,
                        "🤖 <b>Агент включён в этом чате</b>\n\n"
                        "Теперь я отвечаю на все сообщения автоматически.\n"
                        "Могу читать текстовые файлы.\n\n"
                        "<code>-ии агент выкл</code> — выключить",
                        parse_mode=ParseMode.HTML)
                    return

                if sub in ("выкл", "офф", "off"):
                    _agent_chats.discard(chat_id)
                    settings["agent_chats"] = list(_agent_chats)
                    _save_settings(settings)
                    await safe_edit(message, "🤖 Агент выключен в этом чате", parse_mode=ParseMode.HTML)
                    return

                # статус
                agent_list = "\n".join(f"  • <code>{cid}</code>" for cid in sorted(_agent_chats)) or "  нет"
                await safe_edit(message,
                    f"🤖 <b>Агент-режим</b>\n\n"
                    f"Активные чаты:\n{agent_list}",
                    parse_mode=ParseMode.HTML)
                return

            # ── оч ──────────────────────────────────────────────
            if action_word in ("оч", "очистить", "clear"):
                _save_history(chat_id, [])
                await safe_edit(message, "🗑 История этого чата очищена", parse_mode=ParseMode.HTML)
                return

            # ── провайдер ────────────────────────────────────────
            if action_word in ("пров", "провайдер", "provider"):
                if not action_rest:
                    await safe_edit(message,
                        f"Провайдер: <code>{provider}</code>\n\n"
                        "<code>-ии провайдер ollama</code>\n"
                        "<code>-ии провайдер api</code>",
                        parse_mode=ParseMode.HTML)
                    return
                new_p = action_rest.strip().lower()
                if new_p in ("api", "openai", "deepseek"):
                    settings["provider"] = "api"
                    _save_settings(settings)
                    await safe_edit(message,
                        f"✅ Провайдер: <code>api</code>\n\n"
                        f"URL: <code>{settings.get('api_base', 'https://api.deepseek.com')}</code>\n"
                        f"Ключ: {'установлен' if settings.get('api_key') else 'НЕ УСТАНОВЛЕН'}\n\n"
                        "<code>-ии ключ sk-...</code> — установить ключ",
                        parse_mode=ParseMode.HTML)
                elif new_p == "ollama":
                    settings["provider"] = "ollama"
                    _save_settings(settings)
                    await safe_edit(message,
                        f"✅ Провайдер: <code>ollama</code>\n\n"
                        f"URL: <code>{OLLAMA_URL}</code>",
                        parse_mode=ParseMode.HTML)
                else:
                    await safe_edit(message, "❌ Доступно: <code>ollama</code> или <code>api</code>",
                                    parse_mode=ParseMode.HTML)
                return

            # ── ключ ────────────────────────────────────────────
            if action_word in ("ключ", "key"):
                new_key = action_rest.strip()
                if not new_key:
                    key = settings.get("api_key", "")
                    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else ("установлен" if key else "НЕ УСТАНОВЛЕН")
                    await safe_edit(message,
                        f"API ключ: <code>{masked}</code>\n\n"
                        "<code>-ии ключ sk-abc123...</code>",
                        parse_mode=ParseMode.HTML)
                    return
                settings["api_key"] = new_key
                if settings.get("provider", "ollama") == "ollama":
                    settings["provider"] = "api"
                _save_settings(settings)
                await safe_edit(message, "✅ API ключ сохранён", parse_mode=ParseMode.HTML)
                return

            # ── урл ─────────────────────────────────────────────
            if action_word in ("урл", "url"):
                new_url = action_rest.strip()
                if not new_url:
                    await safe_edit(message,
                        f"API URL: <code>{settings.get('api_base', 'https://api.deepseek.com')}</code>\n\n"
                        "<code>-ии урл https://api.deepseek.com</code>",
                        parse_mode=ParseMode.HTML)
                    return
                settings["api_base"] = new_url
                _save_settings(settings)
                await safe_edit(message, f"✅ URL: <code>{new_url}</code>", parse_mode=ParseMode.HTML)
                return

            # ── мод ─────────────────────────────────────────────
            if action_word in ("мод", "модель", "model"):
                new_model = action_rest.strip()
                if not new_model:
                    await safe_edit(message,
                        f"Текущая модель: <code>{settings.get('model', '')}</code>\n\n"
                        "<code>-ии мод deepseek-chat</code>",
                        parse_mode=ParseMode.HTML)
                    return
                settings["model"] = new_model
                _save_settings(settings)
                await safe_edit(message, f"✅ Модель: <code>{new_model}</code>", parse_mode=ParseMode.HTML)
                return

            # ── статус ──────────────────────────────────────────
            if action_word in ("ст", "статус", "status"):
                lines = [f"<b>AI статус</b>\n"]
                lines.append(f"Провайдер: <code>{provider}</code>")
                lines.append(f"Модель: <code>{settings.get('model', '')}</code>")

                if provider == "api":
                    lines.append(f"URL: <code>{settings.get('api_base', '')}</code>")
                    key = settings.get("api_key", "")
                    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else ("да" if key else "❌ нет")
                    lines.append(f"Ключ: {masked}")

                    ok, models = await _check_api(settings.get("api_base", ""), settings.get("api_key", ""))
                    if ok:
                        models_str = "\n".join(f"  • <code>{m}</code>" for m in sorted(models)[:10])
                        lines.append(f"\n🟢 API работает\nМодели:\n{models_str}")
                    else:
                        lines.append("\n🔴 API недоступен")
                else:
                    lines.append(f"URL: <code>{OLLAMA_URL}</code>")
                    ok, models = await _check_ollama()
                    if ok:
                        models_str = "\n".join(f"  • <code>{m}</code>" for m in models[:10])
                        lines.append(f"\n🟢 Ollama работает\nМодели:\n{models_str}")
                    else:
                        lines.append("\n🔴 Ollama не запущена")

                lines.append(f"\nАгент-чаты: {len(_agent_chats)}")
                lines.append(f"Авто-ответ: {'вкл' if _chat_enabled else 'выкл'}")

                await safe_edit(message, "\n".join(lines), parse_mode=ParseMode.HTML)
                return

            # ── система ─────────────────────────────────────────
            if action_word in ("сис", "система", "sys"):
                new_sys = action_rest.strip()
                if not new_sys:
                    await safe_edit(message,
                        f"Системный промпт:\n\n<i>{settings.get('system', DEFAULT_SYSTEM)}</i>\n\n"
                        "<code>-ии сис Ты весёлый бот</code>",
                        parse_mode=ParseMode.HTML)
                    return
                settings["system"] = new_sys
                _save_settings(settings)
                await safe_edit(message, f"✅ Промпт обновлён", parse_mode=ParseMode.HTML)
                return

            # ── анализ ───────────────────────────────────────────
            if action_word in ("ан", "анализ", "analyze"):
                await _handle_analyze(client, message, action_rest)
                return

            # ── сводка ─────────────────────────────────────────
            if action_word in ("св", "сводка", "summary"):
                await _handle_summary(client, message, action_rest)
                return

            # ── справка ─────────────────────────────────────────
            if not action:
                await safe_edit(message,
                    "<b>🤖 AI Chat</b>\n\n"
                    "<code>-ии &lt;текст&gt;</code> — спросить AI\n"
                    "<code>-ии вкл/выкл</code> — авто-ответ\n"
                    "<code>-ии агент вкл/выкл</code> — агент\n"
                    "<code>-ии оч</code> — очистить историю чата\n\n"
                    "<b>Настройки API:</b>\n"
                    "<code>-ии провайдер api</code>\n"
                    "<code>-ии ключ sk-...</code>\n"
                    "<code>-ии урл https://...</code>\n"
                    "<code>-ии мод deepseek-chat</code>\n"
                    "<code>-ии ст</code> — статус\n"
                    "<code>-ии сис &lt;текст&gt;</code> — характер",
                    parse_mode=ParseMode.HTML)
                return

            # ── авто-определение анализа ────────────────────────
            intent = _detect_analyze_intent(action)
            if intent["type"] == "chat":
                await _handle_summary(client, message, str(intent["count"]))
                return
            if intent["type"] == "user":
                target = f"@{intent['username']}" if intent["username"] else ""
                await _handle_analyze(client, message, f"{target} {intent['count']}".strip())
                return
            if intent["type"] == "reply":
                if message.reply_to_message and message.reply_to_message.from_user:
                    u = message.reply_to_message.from_user
                    target = f"@{u.username}" if u.username else str(u.id)
                    await _handle_analyze(client, message, f"{target} {intent['count']}".strip())
                    return

            # ── вопрос к AI ─────────────────────────────────────
            question = args[1].strip()
            history = _load_history(chat_id)

            thinking_msg = await safe_edit(message, "🤔 Думаю...", parse_mode=ParseMode.HTML)
            if not thinking_msg:
                thinking_msg = await message.reply("🤔 Думаю...", quote=True)

            answer = await _ask_ai(question, settings, history)

            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})
            _save_history(chat_id, history)

            answer = _truncate_text(answer)
            try:
                await thinking_msg.edit_text(answer, parse_mode=ParseMode.HTML,
                                              disable_web_page_preview=True)
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

    # group 0 — команда -ии
    client.add_handler(MessageHandler(ai_handler, cmd("ии")))

    # ── авто-ответ на свои сообщения ────────────────────────────
    async def auto_reply(client, message: Message):
        if not _chat_enabled:
            return
        text = message.text or message.caption
        if not text or not text.strip():
            return
        if text.strip().startswith("."):
            return

        try:
            chat_id = message.chat.id
            settings = _load_settings()
            history = _load_history(chat_id)

            thinking = await message.reply("🤔 Думаю...", quote=True)
            answer = await _ask_ai(text, settings, history)

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": answer})
            _save_history(chat_id, history)

            answer = _truncate_text(answer)
            try:
                await thinking.edit_text(answer, parse_mode=ParseMode.HTML,
                                          disable_web_page_preview=True)
            except Exception:
                try:
                    await thinking.reply(answer, quote=False)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"auto_reply error: {e}", exc_info=True)

    client.add_handler(MessageHandler(
        auto_reply,
        filters.me & ~cmd_neg("ии"),
    ), group=1)

    # ── агент-режим ─────────────────────────────────────────────
    async def agent_handler(client, message: Message):
        chat_id = message.chat.id
        if chat_id not in _agent_chats:
            return

        # Не отвечать на свои сообщения
        if message.from_user and message.from_user.is_self:
            return

        # Не отвечать на каналы/анонимов без текста
        text = message.text or message.caption or ""
        if not text.strip() and not message.document:
            return

        # Кулдаун
        import time as _time
        now = _time.time()
        last = _last_agent_reply.get(chat_id, 0)
        if now - last < AGENT_COOLDOWN:
            return

        try:
            _last_agent_reply[chat_id] = now
            settings = _load_settings()
            history = _load_history(chat_id)

            # Определяем кто пишет
            sender = "Кто-то"
            if message.from_user:
                sender = message.from_user.first_name or "Кто-то"

            # Если есть файл — пробуем прочитать
            prompt_parts = []
            if _is_text_file(message):
                result = await _extract_file_content(message)
                if result:
                    fname, content = result
                    prompt_parts.append(f"Пользователь {sender} отправил файл «{fname}»:")
                    prompt_parts.append(f"```\n{content}\n```")
                    prompt_parts.append("Ответь на содержимое файла.")

            if text.strip():
                if not prompt_parts:
                    prompt_parts.append(f"[{sender}]: {text}")
                else:
                    prompt_parts.append(f"[{sender}]: {text}")

            if not prompt_parts:
                return

            prompt = "\n".join(prompt_parts)

            thinking = await message.reply("🤔", quote=True)
            answer = await _ask_ai(prompt, settings, history)

            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": answer})
            _save_history(chat_id, history)

            answer = _truncate_text(answer)
            try:
                await thinking.edit_text(answer, parse_mode=ParseMode.HTML,
                                          disable_web_page_preview=True)
            except Exception:
                try:
                    await thinking.reply(answer, quote=False)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"agent error: {e}", exc_info=True)

    # group 1 — агент (после всех команд)
    client.add_handler(MessageHandler(
        agent_handler,
        filters.me & ~cmd_neg("ии"),
    ), group=1)


def on_load():
    global _agent_chats
    s = _load_settings()
    _agent_chats = set(s.get("agent_chats", []))
    provider = s.get("provider", "ollama")
    model = s.get("model", "")
    print(f"[AIChat] Loaded. provider={provider}, model={model}, agents={len(_agent_chats)}")


def on_unload():
    global _chat_enabled
    _chat_enabled = False
    print("[AIChat] Unloaded")
