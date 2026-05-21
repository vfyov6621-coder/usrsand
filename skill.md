# sandusr — Руководство по созданию скриптов

## Общая архитектура

sandusr — Telegram юзербот на Pyrofork (форк Pyrogram). Скрипты — это плагины, которые
подгружаются динамически при старте (или через команду `.lm`). Каждый скрипт живет в своей
папке внутри `scripts/` и должен содержать `main.py` с функцией `register(client)`.

```
usrsand/
├── main.py              # точка входа, регистрация хендлеров, запуск
├── config.py            # настройка (API_ID, API_HASH, PROXY и т.д.)
├── loader.py            # динамическая загрузка/выгрузка скриптов
├── web.py               # веб-панель (Flask)
├── bot_photo.jpg        # фото для меню .mm (опционально)
├── requirements.txt
├── start.bat
└── scripts/
    ├── _utils.py        # общие утилиты (safe_edit)
    ├── ping/
    │   └── main.py      # пример: простейший скрипт
    ├── notes/
    │   └── main.py      # пример: скрипт с сохранением данных
    ├── weather/
    │   └── main.py      # пример: HTTP-запросы
    ├── translator/
    │   ├── main.py
    │   └── addons/      # пример: аддоны к скрипту
    │       ├── ru.py
    │       ├── de.py
    │       └── ...
    └── ai_chat/
        ├── main.py
        ├── history.json  # данные скрипта (создаются автоматически)
        └── settings.json
```

---

## Как работает загрузчик (loader.py)

При старте `loader.py` сканирует `scripts/` и для каждой подпапки (не начинающейся с `_`),
в которой есть `main.py`, выполняет:

1. `importlib.util.spec_from_file_location()` — создаёт модуль
2. `spec.loader.exec_module(module)` — исполняет код main.py (определения функций)
3. `module.register(client)` — вызывает `register()`, где скрипт добавляет хендлеры
4. `module.on_load()` — вызывает `on_load()` если есть (инициализация)
5. Сканирует `addons/` внутри папки скрипта и грузит каждый `.py` файл аналогично

**Важно**: код модуля (импорты, определения) выполняется при загрузке.
Функция `register()` вызывается отдельно — именно там нужно добавлять хендлеры.
Не добавляй хендлеры на уровне модуля (вне функций), потому что `client` там недоступен.

---

## Структура скрипта (минимум)

Каждый скрипт — это папка в `scripts/` с файлом `main.py`. Минимальный пример:

```python
# scripts/myscript/main.py
"""MyScript — описание что делает скрипт."""

def register(client):
    """Регистрация хендлеров. Вызывается loader'ом при загрузке."""
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    async def my_handler(client, message: Message):
        await safe_edit(message, "Работает!")

    client.add_handler(MessageHandler(
        my_handler,
        filters.command("hello", prefixes=".") & filters.me,
    ))

def on_load():
    """Вызывается после register(). Для инициализации."""
    print("[myscript] Loaded. .hello")

def on_unload():
    """Вызывается при выгрузке (.lm unload myscript). Для очистки."""
    print("[myscript] Unloaded")
```

### Обязательное:
- **`register(client)`** — без неё скрипт не добавит никаких хендлеров

### Опциональное:
- **`on_load()`** — инициализация при загрузке (загрузка данных, print в консоль)
- **`on_unload()`** — очистка при выгрузке (закрытие соединений, сброс состояния)
- **Докстринг модуля** (первая строка с `"""`) — используется как описание в `.lm info`

---

## Папка скрипта: файлы и данные

Скрипт может хранить файлы рядом со своим `main.py`:

```python
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "mydata.json")

def _load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

Для данных которые юзер может редактировать, используй отдельную папку:

```python
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "scripts_custom")
# scripts_custom/mydata.json
```

---

## Хендлеры и фильтры

### Регистрация хендлера

Все импорты Pyrogram делай **внутри `register()`**, а не на уровне модуля. Это важно,
потому что при импорте модуля клиент ещё не создан, а типы могут вызывать ошибки.

```python
def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message

    async def my_handler(client, message: Message):
        ...

    client.add_handler(MessageHandler(
        my_handler,
        filters.command("cmd", prefixes=".") & filters.me,
    ))
```

### Доступные типы хендлеров:
- **`MessageHandler`** — текстовые сообщения
- **`CallbackQueryHandler`** — нажатия inline-кнопок

```python
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
```

### Полезные фильтры:

```python
# Команда (только свои сообщения)
filters.command("ping", prefixes=".") & filters.me

# Команда + только reply
filters.command("cmd", prefixes=".") & filters.me & filters.reply

# Ответ на сообщение
filters.reply & filters.me

# Любое своё сообщение (не команда)
filters.me & ~filters.command(prefixes=".")

# Конкретный чат
filters.chat(-1001234567890)

# Callback по regex
filters.regex(r"^mybtn_")
```

### Группы хендлеров:
- **group=0** (по умолчанию) — выполняются первыми
- **group=1** — выполняются после group=0
- Можно использовать чтобы один хендлер «перехватывал» сообщения после команд:

```python
# Команда — group 0 (по умолчанию)
client.add_handler(MessageHandler(
    cmd_handler,
    filters.command("ai", prefixes=".") & filters.me,
))

# Авто-ответчик — group 1 (после всех команд)
client.add_handler(MessageHandler(
    auto_responder,
    filters.me & ~filters.command(["ai"], prefixes="."),
), group=1)
```

---

## safe_edit — безопасное редактирование сообщений

`scripts/_utils.py` содержит `safe_edit(message, text, **kwargs)`:
- Пытается `message.edit_text(text)`
- Если не получается (например ChatWriteForbidden в канале) — отправляет `message.reply(text)`
- Это **всегда** нужно использовать вместо `message.edit_text()`

```python
from scripts._utils import safe_edit

# Просто текст
await safe_edit(message, "Привет!")

# С HTML-форматированием
await safe_edit(message, "<b>Жирный</b> и <code>код</code>", parse_mode=ParseMode.HTML)

# Отключить превью ссылок
await safe_edit(message, "Текст", parse_mode=ParseMode.HTML, disable_web_page_preview=True)
```

**Всегда** указывай `parse_mode=ParseMode.HTML` если используешь HTML-теги.

---

## Работа с сообщениями

### Парсинг аргументов команды:

```python
# .cmd arg1 arg2 arg3
args = message.text.split(maxsplit=2)
# args[0] = ".cmd"
# args[1] = "arg1"
# args[2] = "arg2 arg3" (если maxsplit=2)

# Или:
parts = message.text.split()
command = parts[0]  # ".cmd"
if len(parts) > 1:
    arg1 = parts[1]
```

### Ответ на сообщение (reply):

```python
reply = message.reply_to_message
if reply:
    reply_text = reply.text or reply.caption or ""
    reply_user = reply.from_user
    if reply_user:
        user_id = reply_user.id
        username = reply_user.username
        name = reply_user.first_name
```

### Отправка ответов:

```python
# Ответить на сообщение
await message.reply("Ответ", quote=True)

# Отправить в чат (без привязки к сообщению)
await message.reply_text("Текст")

# Отправить фото
await message.reply_photo(photo, caption="Подпись")

# Скачать фото/файл из сообщения
file_path = await client.download_media(message.photo.file_id, file_name="photo.jpg")
```

### Доступные поля сообщения:

```python
message.text           # текст сообщения
message.caption        # подпись к медиа
message.from_user      # объект User (отправитель)
message.chat           # объект Chat
message.chat.id        # ID чата
message.date           # datetime отправки
message.reply_to_message  # объект Message или None
message.photo          # список размеров фото (или None)
message.video          # видео
message.sticker        # стикер
message.voice          # голосовое
message.document       # файл
message.animation      # GIF
message.audio          # аудио
```

---

## HTTP-запросы (ВАЖНО!)

### Правило #1: НЕ используй `requests`, `aiohttp` или `deep_translator`
для запросов к внешним API. Они не используют прокси из `.env` и не проходят через VPN
на Windows. Google, YouTube и многие сервисы заблокированы в РФ.

### Правило #2: Используй `urllib.request` (встроенный модуль)
Он работает через системный прокси/VPN и не требует дополнительных зависимостей.

```python
import urllib.request
import urllib.parse
import urllib.error
import json

def _http_get(url, timeout=15):
    """Синхронный HTTP GET. Вызывать через run_in_executor."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
```

### Внутри async хендлера — оборачивай в `run_in_executor`:

```python
import asyncio

async def handler(client, message: Message):
    # Показать загрузку
    await safe_edit(message, "Загрузка...")

    # Синхронный запрос в фоне
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _http_get, "https://api.example.com/data")

    # Обработать результат
    await safe_edit(message, f"Результат: {data['value']}")
```

### Для POST-запросов:

```python
def _http_post(url, payload, timeout=15):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
```

### Бесплатные API (работают без VPN из РФ):
- **MyMemory** — перевод: `https://api.mymemory.translated.net/get?q=text&langpair=en|ru`
- **Open-Meteo** — погода: `https://api.open-meteo.com/v1/forecast`
- **Wikipedia** — `https://ru.wikipedia.org/api/rest_v1/page/summary/Тема`
- **IPinfo** — `https://ipinfo.io/json`

---

## HTML-форматирование в Telegram

Всегда используй `parse_mode=ParseMode.HTML` и экранируй спецсимволы:

```python
await safe_edit(message, text, parse_mode=ParseMode.HTML)
```

### Теги:
```html
<b>жирный</b>
<i>курсив</i>
<code>код</code>
<pre>блок кода</pre>
<s>зачёркнутый</s>
<u>подчёркнутый</u>
<a href="https://example.com">ссылка</a>
```

### Экранирование:
Для пользовательского текста оборачивай в `<code>` или используй `html.escape()`:

```python
from html import escape
safe_text = escape(user_text)
await safe_edit(message, f"<code>{safe_text}</code>", parse_mode=ParseMode.HTML)
```

### Ограничения Telegram:
- Максимум **4096 символов** на сообщение
- Используй `_truncate_text()` для обрезки:

```python
def _truncate_text(text: str, max_len: int = 4096) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 20] + "\n\n[...] сообщение обрезано"
```

---

## Callback-кнопки (inline-кнопки)

```python
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler, CallbackQueryHandler
    from pyrogram.enums import ParseMode

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Кнопка 1", callback_data="mybtn_1")],
        [InlineKeyboardButton("Кнопка 2", callback_data="mybtn_2")],
    ])

    async def cmd_handler(client, message):
        await safe_edit(message, "Выбери:", reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def callback_handler(client, callback):
        data = callback.data
        if data == "mybtn_1":
            await callback.message.edit_text("Нажата кнопка 1")
        elif data == "mybtn_2":
            await callback.message.edit_text("Нажата кнопка 2")
        await callback.answer()  # убрать «часики» на кнопке

    client.add_handler(MessageHandler(
        cmd_handler,
        filters.command("menu", prefixes=".") & filters.me,
    ))
    client.add_handler(CallbackQueryHandler(
        callback_handler,
        filters.regex(r"^mybtn_"),
    ))
```

### Правила callback_data:
- Максимум **64 байта**
- Используй префикс (имя скрипта) чтобы не конфликтовать: `"myscript_action_id"`
- Можно использовать regex-фильтр для перехвата: `filters.regex(r"^myscript_")`

---

## Аддоны (дополнительные модули к скрипту)

Аддоны — это `.py` файлы в папке `scripts/<имя>/addons/`. Они загружаются автоматически
после основного скрипта и имеют ту же структуру (register, on_load, on_unload).

```
scripts/translator/
├── main.py            # основная команда .tr
└── addons/
    ├── ru.py          # .tra — быстрый перевод на русский
    ├── de.py          # .trd — быстрый перевод на немецкий
    └── zh.py          # .trz — быстрый перевод на китайский
```

### Структура аддона:

```python
# scripts/translator/addons/ru.py
"""Translator addon: Russian (.tra)"""

def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    async def tra_handler(client, message: Message):
        # Обработка команды .tra
        await safe_edit(message, "Перевод на русский...")

    client.add_handler(MessageHandler(
        tra_handler,
        filters.command("tra", prefixes=".") & filters.me,
    ))

def on_load():
    print("[translator/ru] Loaded. .tra")
```

### Особенности:
- Аддон — это обычный `.py` файл, не папка
- Loader автоматически вызывает `register(client)`, `on_load()`, `on_unload()` у аддона
- При `.lm unload translator` выгружаются и все аддоны
- При `.lm reload translator` перезагружаются и аддоны
- Аддон может использовать любые импорты основного скрипта (они в одном sys.path)

---

## Работа с Telegram API через client

Внутри хендлеров `client` — это Pyrofork Client. Основные методы:

```python
# Получить информацию о юзере
user = await client.get_users("username")  # по @username
user = await client.get_users(123456789)   # по ID

# История чата
async for msg in client.get_chat_history(chat_id, limit=100):
    print(msg.text)

# Скачать медиа
path = await client.download_media(message.photo.file_id, file_name="photo.jpg")
path = await client.download_media(message.document.file_id)

# Отправить сообщение
await client.send_message(chat_id, "Текст")

# Удалить сообщение
await message.delete()

# Переслать
await message.forward(chat_id)

# Ответить
await message.reply("Ответ", quote=True)
```

---

## Отладка и логирование

```python
import logging

log = logging.getLogger("sandusr.scripts.myscript")

# Внутри хендлера:
log.info("Команда вызвана")
log.error(f"Ошибка: {e}", exc_info=True)
log.warning("Предупреждение")

# В консоль (при загрузке):
def on_load():
    print("[myscript] Loaded. .cmd — описание")
```

Логирование настраивается в `main.py` — все логи пишутся в консоль и в веб-панель
(если включена). Для ошибок в хендлерах **всегда** используй try/except:

```python
async def my_handler(client, message: Message):
    try:
        # ... логика ...
    except Exception as e:
        log.error(f"my_handler error: {e}", exc_info=True)
        try:
            await safe_edit(message, f"Ошибка: {str(e)[:200]}")
        except Exception:
            pass
```

---

## Важные правила и антипаттерны

### ДЕЛАЙ:
- Импортируй Pyrogram **внутри `register()`**, а не на уровне модуля
- Используй `safe_edit()` вместо `message.edit_text()`
- Оборачивай HTTP-запросы в `run_in_executor()`
- Используй `urllib.request` вместо `requests`/`aiohttp`
- Обрезай длинный текст до 4096 символов
- Обрабатывай ошибки (try/except) в каждом хендлере
- Используй `from __future__ import annotations` если есть проблемы с типами

### НЕ ДЕЛАЙ:
- Не добавляй хендлеры на уровне модуля (вне `register()`)
- Не используй `requests` или `deep_translator` (Google заблокирован в РФ)
- Не делай блокирующих операций (HTTP, файлы) без `run_in_executor()`
- Не храни пароли/токены в коде (используй `.env`)
- Не используй синхронный `time.sleep()` в async функциях (используй `asyncio.sleep()`)

---

## Шаблоны скриптов

### Шаблон #1: Простой хендлер (как ping)

```python
"""CommandName — краткое описание."""

def register(client):
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.commandname")

    async def handler(client, message: Message):
        try:
            # Ваша логика здесь
            await safe_edit(message, "Ответ")
        except Exception as e:
            log.error(f"error: {e}", exc_info=True)

    client.add_handler(MessageHandler(
        handler,
        filters.command("cmd", prefixes=".") & filters.me,
    ))

def on_load():
    print("[commandname] Loaded. .cmd")
```

### Шаблон #2: Команда с подкомандами (как notes)

```python
"""Notes — пример скрипта с подкомандами и сохранением данных."""
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")

def _load():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def register(client):
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.notes")

    async def handler(client, message: Message):
        try:
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                # Справка
                await safe_edit(message,
                    "<b>Заметки:</b>\n\n"
                    "<code>.note save имя текст</code>\n"
                    "<code>.note get имя</code>\n"
                    "<code>.note list</code>\n"
                    "<code>.note del имя</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            action = args[1].lower()

            if action == "save":
                if len(args) < 3:
                    await safe_edit(message, "Формат: <code>.note save имя текст</code>", parse_mode=ParseMode.HTML)
                    return
                parts = args[2].strip().split(maxsplit=1)
                name = parts[0]
                text = parts[1] if len(parts) > 1 else ""
                data = _load()
                data[name] = text
                _save(data)
                await safe_edit(message, f"Сохранено: <b>{name}</b>", parse_mode=ParseMode.HTML)

            elif action == "list":
                data = _load()
                if not data:
                    await safe_edit(message, "Заметок нет", parse_mode=ParseMode.HTML)
                else:
                    lines = "\n".join(f"  <code>{k}</code>" for k in sorted(data.keys()))
                    await safe_edit(message, f"<b>Заметки:</b>\n\n{lines}", parse_mode=ParseMode.HTML)

            elif action == "get":
                if len(args) < 3:
                    await safe_edit(message, "Формат: <code>.note get имя</code>", parse_mode=ParseMode.HTML)
                    return
                name = args[2].strip()
                data = _load()
                if name in data:
                    await safe_edit(message, f"<b>{name}:</b>\n\n{data[name]}", parse_mode=ParseMode.HTML)
                else:
                    await safe_edit(message, f"Не найдено: <b>{name}</b>", parse_mode=ParseMode.HTML)

            elif action == "del":
                if len(args) < 3:
                    await safe_edit(message, "Формат: <code>.note del имя</code>", parse_mode=ParseMode.HTML)
                    return
                name = args[2].strip()
                data = _load()
                if name in data:
                    del data[name]
                    _save(data)
                    await safe_edit(message, f"Удалено: <b>{name}</b>", parse_mode=ParseMode.HTML)
                else:
                    await safe_edit(message, f"Не найдено: <b>{name}</b>", parse_mode=ParseMode.HTML)
            else:
                await safe_edit(message, "Неизвестная команда. .note для справки", parse_mode=ParseMode.HTML)

        except Exception as e:
            log.error(f"error: {e}", exc_info=True)
            try:
                await safe_edit(message, f"Ошибка: {str(e)[:200]}")
            except Exception:
                pass

    client.add_handler(MessageHandler(
        handler,
        filters.command("note", prefixes=".") & filters.me,
    ))

def on_load():
    print("[notes] Loaded. .note save/get/list/del")
```

### Шаблон #3: HTTP-запрос + данные из reply (как translator)

```python
"""MyAPI — запрос к внешнему API с данными из reply или аргументов."""
import urllib.request
import json

API_URL = "https://api.example.com/v1/translate"

def _api_call(text, target_lang):
    """Синхронный запрос к API."""
    url = f"{API_URL}?q={urllib.parse.quote(text)}&lang={target_lang}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def register(client):
    import asyncio
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.myapi")

    async def handler(client, message: Message):
        try:
            args = message.text.split(maxsplit=1)

            # Получить текст: из аргументов или из reply
            text = None
            if len(args) > 1:
                text = args[1].strip()
            elif message.reply_to_message:
                text = message.reply_to_message.text or message.reply_to_message.caption

            if not text:
                await safe_edit(message,
                    "Использование: <code>.myapi текст</code>\n"
                    "Или ответьте на сообщение: <code>.myapi</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            await safe_edit(message, "Обработка...")

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, _api_call, text, "ru")

            answer = result.get("result", "Нет ответа")
            await safe_edit(message, f"<b>Результат:</b>\n\n<code>{answer}</code>", parse_mode=ParseMode.HTML)

        except Exception as e:
            log.error(f"error: {e}", exc_info=True)
            try:
                await safe_edit(message, f"Ошибка: {str(e)[:200]}")
            except Exception:
                pass

    client.add_handler(MessageHandler(
        handler,
        filters.command("myapi", prefixes=".") & filters.me,
    ))

def on_load():
    print("[myapi] Loaded. .myapi [text|reply]")
```

### Шаблон #4: Inline-кнопки + callback

```python
"""MyMenu — пример меню с inline-кнопками."""
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def register(client):
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler, CallbackQueryHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.mymenu")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Опция 1", callback_data="mymenu_opt1")],
        [InlineKeyboardButton("Опция 2", callback_data="mymenu_opt2")],
        [InlineKeyboardButton("Закрыть", callback_data="mymenu_close")],
    ])

    async def cmd_handler(client, message: Message):
        try:
            await safe_edit(
                message,
                "<b>Меню:</b>\n\nВыберите опцию:",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            log.error(f"error: {e}")

    async def cb_handler(client, callback):
        try:
            data = callback.data
            if data == "mymenu_opt1":
                await callback.message.edit_text("Вы выбрали опцию 1")
            elif data == "mymenu_opt2":
                await callback.message.edit_text("Вы выбрали опцию 2")
            elif data == "mymenu_close":
                await callback.message.edit_text("Меню закрыто")
            await callback.answer()
        except Exception as e:
            log.error(f"callback error: {e}")

    client.add_handler(MessageHandler(
        cmd_handler,
        filters.command("menu", prefixes=".") & filters.me,
    ))
    client.add_handler(CallbackQueryHandler(
        cb_handler,
        filters.regex(r"^mymenu_"),
    ))

def on_load():
    print("[mymenu] Loaded. .menu")
```

---

## Управление скриптами через Telegram

| Команда | Описание |
|---------|----------|
| `.lm` | Справка по управлению |
| `.lm list` | Список всех скриптов (загруженные + доступные) |
| `.lm load <name>` | Загрузить скрипт |
| `.lm unload <name>` | Выгрузить скрипт |
| `.lm reload <name>` | Перезагрузить скрипт (изменения в коде) |
| `.lm info <name>` | Информация о скрипте |

---

## Именование

- Папка скрипта: `scripts/my_command/` — snake_case, коротко
- Команда: `.mycmd` — короткая, легко набрать
- Аддон: короткая команда вида `.trru` (translator → ru), `.noteq` и т.д.
- Префикс callback: `имя_скрипта_действие` — чтобы не было конфликтов
- Логгер: `sandusr.scripts.имя_скрипта`

---

## Полезные ресурсы

- **Pyrogram docs**: https://docs.pyrogram.org/
- **Pyrofork** (используется вместо Pyrogram): форк с улучшениями
- **Telegram HTML formatting**: https://core.telegram.org/bots/api#html-style
- **Filters**: https://docs.pyrogram.org/api/filters
- **Types**: https://docs.pyrogram.org/api/types
