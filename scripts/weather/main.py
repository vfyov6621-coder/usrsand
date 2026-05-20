"""Weather — weather info with ASCII art. .wea <city>"""

import asyncio
import urllib.request
import urllib.parse
import urllib.error
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from scripts._utils import safe_edit

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: ("Ясно", "sun"), 1: ("Преимущественно ясно", "sun_cloud"),
    2: ("Переменная облачность", "cloud"), 3: ("Пасмурно", "overcast"),
    45: ("Туман", "fog"), 48: ("Изморозь", "fog"),
    51: ("Лёгкая морось", "drizzle"), 53: ("Морось", "drizzle"), 55: ("Сильная морось", "rain"),
    61: ("Небольшой дождь", "drizzle"), 63: ("Дождь", "rain"), 65: ("Сильный дождь", "rain"),
    71: ("Небольшой снег", "snow"), 73: ("Снег", "snow"), 75: ("Сильный снег", "snow"),
    80: ("Небольшой ливень", "rain"), 81: ("Ливень", "rain"), 82: ("Сильный ливень", "rain"),
    85: ("Небольшой снегопад", "snow"), 86: ("Сильный снегопад", "snow"),
    95: ("Гроза", "thunder"), 96: ("Гроза с градом", "thunder"), 99: ("Сильная гроза", "thunder"),
}

ART = {
    "sun": "    \\   /    \n     .---.    \n  ,-|     |-. \n (  |     |  )\n  `'-|     |-'`\n     '---'    \n",
    "sun_cloud": "   \\  /  \u2601\ufe0f   \n    .--.     \n .(    ).    \n(   .--.  )  \n `-(    )-'  \n    `--'     \n",
    "cloud": "     \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f     \n   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n    \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f    \n      \u2601\ufe0f\u2601\ufe0f     \n",
    "overcast": "  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f \n\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f \n \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f \n  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n",
    "fog": "  _  _  _  _  \n / \\ / \\ / \\ / \\\n|M|I|S|T| | |\n \\_/ \\_/ \\_/ \\_/\n  _  _  _  _  \n / \\ / \\ / \\ / \\\n",
    "drizzle": "   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n    \u00b7  \u00b7  \u00b7   \n   \u00b7  \u00b7  \u00b7  \u00b7 \n  \u00b7  \u00b7  \u00b7  \u00b7  \n",
    "rain": "   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  :  :  :  :  \n :  :  :  :   \n:  :  :  :    \n",
    "snow": "   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  *  *  *  *  \n *  *  *  *   \n*  *  *  *    \n",
    "thunder": "   \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f   \n  \u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f\u2601\ufe0f  \n   \u2601\ufe0f /\\ \u2601\ufe0f    \n    /  \\     \n   / \u2601\ufe0f \\     \n  \u26a1    \u26a1    \n",
}

EMOJI = {"sun": "\u2600\ufe0f", "sun_cloud": "\ud83c\udf24\ufe0f", "cloud": "\u26c5", "overcast": "\u2601\ufe0f", "fog": "\ud83c\udf2b\ufe0f", "drizzle": "\ud83c\udf26\ufe0f", "rain": "\ud83c\udf27\ufe0f", "snow": "\u2744\ufe0f", "thunder": "\u26c8\ufe0f"}


def _wmo(code):
    name, key = WMO.get(code, ("Неизвестно", "sun"))
    return name, key, ART.get(key, ART["sun"]), EMOJI.get(key, "\ud83c\udf21\ufe0f")


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def register(client):
    @client.on_message(filters.command("wea", prefixes=".") & filters.me)
    async def wea_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await safe_edit(message, "<b>\ud83c\udf26 Погода</b>\n\n<code>.wea &lt;город&gt;</code>", parse_mode=ParseMode.HTML)
            return

        city = args[1].strip()
        await safe_edit(message, f"\ud83d\udd04 Загрузка погоды: <b>{city}</b>...", parse_mode=ParseMode.HTML)

        try:
            loop = asyncio.get_running_loop()
            geo_params = urllib.parse.urlencode({"name": city, "count": 1, "language": "ru", "format": "json"})
            geo_data = await loop.run_in_executor(None, _http_get, f"{GEO_URL}?{geo_params}")

            results = geo_data.get("results")
            if not results:
                await safe_edit(message, f"\u274c Город <b>{city}</b> не найден", parse_mode=ParseMode.HTML)
                return

            loc = results[0]
            lat, lon = loc["latitude"], loc["longitude"]
            found_name = loc.get("name", city)
            region = loc.get("admin1", "")
            country = loc.get("country", "")

            w_params = urllib.parse.urlencode({
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            })
            w_data = await loop.run_in_executor(None, _http_get, f"{WEATHER_URL}?{w_params}")

            cur = w_data["current"]
            temp = cur.get("temperature_2m", "?")
            feels = cur.get("apparent_temperature", "?")
            humidity = cur.get("relative_humidity_2m", "?")
            wind = cur.get("wind_speed_10m", "?")
            condition, art_key, ascii_art, emoji = _wmo(cur.get("weather_code", 0))

            location = f"\ud83c\udf0d <b>{found_name}</b>"
            if region:
                location += f", {region}"
            if country:
                location += f", {country}"

            text = (
                f"{location}\n\n<pre>{ascii_art}</pre>\n"
                f"{emoji} <b>{condition}</b>\n"
                f"\ud83c\udf21 Температура: <b>{temp}\u00b0C</b>\n"
                f"\ud83e\udd12 Ощущается: <b>{feels}\u00b0C</b>\n"
                f"\ud83d\udca7 Влажность: <b>{humidity}%</b>\n"
                f"\ud83d\udca8 Ветер: <b>{wind} км/ч</b>"
            )
            await safe_edit(message, text, parse_mode=ParseMode.HTML)

        except (asyncio.TimeoutError, TimeoutError):
            await safe_edit(message, "\u274c Таймаут.", parse_mode=ParseMode.HTML)
        except urllib.error.URLError as e:
            await safe_edit(message, f"\u274c Ошибка сети: {e.reason}", parse_mode=ParseMode.HTML)
        except Exception as e:
            await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)


def on_load():
    print("[weather] Loaded. .wea <city>")
