# sandusr — Telegram Userbot v3.0

Модульный Telegram юзербот на Pyrofork с веб-панелью.

## Установка

1. Клонируй репозиторий
2. Создай `.env` файл:
```
API_ID=your_api_id
API_HASH=your_api_hash
PHONE=+79991234567
```
3. Установи зависимости: `pip install -r requirements.txt`
4. Запусти: `python main.py`
5. Веб-панель: `http://localhost:8080`

## Команды

| Команда | Описание |
|---------|----------|
| `.mm` | Меню бота |
| `.ping` | Пинг |
| `.note` | Заметки (save/get/list/del/set) |
| `.n <name>` | Быстрый вызов заметки |
| `.wea <city>` | Погода |
| `.tr [lang] <text>` | Перевод |
| `.tra/.trd/.trz/.trf/.tru/.trb` | Перевод (ответ на соо) |
| `.ai <text>` | AI ассистент (требует Ollama) |

## Веб-панель

Панель доступна на `http://localhost:8080` после запуска. Показывает:
- Статус бота и аптайм
- Загруженные модули
- Логи в реальном времени
- Список всех команд

Порт можно изменить через переменную окружения `PORT`.

## AI Chat

Для `.ai` нужен установленный [Ollama](https://ollama.com):
```
ollama pull qwen2.5:1.5b
ollama serve
```

## Структура

```
main.py              — точка входа
config.py            — конфигурация
loader.py            — загрузчик скриптов
web.py               — веб-панель (Flask)
templates/index.html — дашборд
scripts/             — модули
  _utils.py          — общие утилиты
  ping/              — пинг
  notes/             — заметки
  weather/           — погода
  translator/        — переводчик + аддоны
  ai_chat/           — AI через Ollama
```
