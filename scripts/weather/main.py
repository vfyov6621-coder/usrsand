"""Weather — weather info with ASCII art. -погода <city>"""

import asyncio
import urllib.request
import urllib.parse
import urllib.error

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

EMOJI = {"sun": "☀️", "sun_cloud": "🌤️", "cloud": "⛅", "overcast": "☁️", "fog": "🌫️", "drizzle": "🌦️", "rain": "🌧️", "snow": "❄️", "thunder": "⛈️"}


def _wmo(code):
    name, key = WMO.get(code, ("Неизвестно", "sun"))
    return name, EMOJI.get(key, "🌡️")


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def register(client):
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    from scripts._utils import cmd, safe_edit

    log = logging.getLogger("sandusr.scripts.weather")

    async def wea_handler(client, message: Message):
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await safe_edit(message, "<b>🌦 Погода</b>\n\n<code>-погода &lt;город&gt;</code>", parse_mode=ParseMode.HTML)
                return

            city = args[1].strip()
            await safe_edit(message, f"🔄 Загрузка погоды: <b>{city}</b>...", parse_mode=ParseMode.HTML)

            loop = asyncio.get_running_loop()
            geo_params = urllib.parse.urlencode({"name": city, "count": 1, "language": "ru", "format": "json"})
            geo_data = await loop.run_in_executor(None, _http_get, f"{GEO_URL}?{geo_params}")

            results = geo_data.get("results")
            if not results:
                await safe_edit(message, f"❌ Город <b>{city}</b> не найден", parse_mode=ParseMode.HTML)
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
            condition, emoji = _wmo(cur.get("weather_code", 0))

            location = f"🌍 <b>{found_name}</b>"
            if region:
                location += f", {region}"
            if country:
                location += f", {country}"

            text = (
                f"{location}\n\n"
                f"{emoji} <b>{condition}</b>\n"
                f"🌡 Температура: <b>{temp}°C</b>\n"
                f"🤒 Ощущается: <b>{feels}°C</b>\n"
                f"💧 Влажность: <b>{humidity}%</b>\n"
                f"💨 Ветер: <b>{wind} км/ч</b>"
            )
            await safe_edit(message, text, parse_mode=ParseMode.HTML)

        except (asyncio.TimeoutError, TimeoutError):
            await safe_edit(message, "❌ Таймаут.", parse_mode=ParseMode.HTML)
        except urllib.error.URLError as e:
            await safe_edit(message, f"❌ Ошибка сети: {e.reason}", parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"weather error: {e}", exc_info=True)
            await safe_edit(message, f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML)

    client.add_handler(MessageHandler(
        wea_handler,
        cmd("погода"),
    ))


def on_load():
    print("[weather] Loaded. -погода <city>")
