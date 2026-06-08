"""Weather — текущая погода + прогноз по городу
-погода <город>       — сейчас
-погода п <город>     — прогноз на 7 дней
"""

import asyncio
import urllib.request
import urllib.parse
import urllib.error

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: ("Ясно", "sun"), 1: ("Преим. ясно", "sun_cloud"),
    2: ("Перем. облачность", "cloud"), 3: ("Пасмурно", "overcast"),
    45: ("Туман", "fog"), 48: ("Изморозь", "fog"),
    51: ("Лёгкая морось", "drizzle"), 53: ("Морось", "drizzle"), 55: ("Сильная морось", "rain"),
    61: ("Небольшой дождь", "drizzle"), 63: ("Дождь", "rain"), 65: ("Сильный дождь", "rain"),
    71: ("Небольшой снег", "snow"), 73: ("Снег", "snow"), 75: ("Сильный снег", "snow"),
    80: ("Небольшой ливень", "rain"), 81: ("Ливень", "rain"), 82: ("Сильный ливень", "rain"),
    85: ("Небольшой снегопад", "snow"), 86: ("Сильный снегопад", "snow"),
    95: ("Гроза", "thunder"), 96: ("Гроза с градом", "thunder"), 99: ("Сильная гроза", "thunder"),
}

EMOJI = {
    "sun": "☀️", "sun_cloud": "🌤️", "cloud": "⛅", "overcast": "☁️",
    "fog": "🌫️", "drizzle": "🌦️", "rain": "🌧️", "snow": "❄️", "thunder": "⛈️",
}

# иконки направлений ветра
WIND_DIR = {
    "N": "⬆️", "NE": "↗️", "E": "➡️", "SE": "↘️",
    "S": "⬇️", "SW": "↙️", "W": "⬅️", "NW": "↖️",
}

DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _wmo(code):
    name, key = WMO.get(code, ("Неизвестно", "sun"))
    return name, EMOJI.get(key, "🌡️")


def _wind_dir(deg):
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return WIND_DIR.get(dirs[int((deg % 360) / 45)], "🌡️")


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
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                await safe_edit(message,
                    "<b>Погода</b>\n\n"
                    "<code>-погода &lt;город&gt;</code> — сейчас\n"
                    "<code>-погода п &lt;город&gt;</code> — прогноз на 7 дней",
                    parse_mode=ParseMode.HTML)
                return

            action = args[1].strip().lower()

            # прогноз
            if action == "п":
                if len(args) < 3:
                    await safe_edit(message, "<code>-погода п &lt;город&gt;</code>",
                                    parse_mode=ParseMode.HTML)
                    return
                city = args[2].strip()
                await _forecast(message, city, log)
                return

            # текущая погода
            city = args[1].strip()
            await _current(message, city, log)

        except Exception as e:
            log.error(f"weather error: {e}", exc_info=True)
            await safe_edit(message, f"Ошибка: {e}", parse_mode=ParseMode.HTML)

    async def _current(message, city, log):
        await safe_edit(message, f"Загрузка погоды: <b>{city}</b>...", parse_mode=ParseMode.HTML)

        loop = asyncio.get_running_loop()
        geo_params = urllib.parse.urlencode({"name": city, "count": 1, "language": "ru", "format": "json"})
        geo_data = await loop.run_in_executor(None, _http_get, f"{GEO_URL}?{geo_params}")

        results = geo_data.get("results")
        if not results:
            await safe_edit(message, f"Город <b>{city}</b> не найден", parse_mode=ParseMode.HTML)
            return

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        found_name = loc.get("name", city)
        region = loc.get("admin1", "")
        country = loc.get("country", "")

        w_params = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
        })
        w_data = await loop.run_in_executor(None, _http_get, f"{WEATHER_URL}?{w_params}")

        cur = w_data["current"]
        temp = cur.get("temperature_2m", "?")
        feels = cur.get("apparent_temperature", "?")
        humidity = cur.get("relative_humidity_2m", "?")
        wind = cur.get("wind_speed_10m", "?")
        wind_dir = cur.get("wind_direction_10m", 0)
        condition, emoji = _wmo(cur.get("weather_code", 0))

        location = f"<b>{found_name}</b>"
        if region:
            location += f", {region}"
        if country:
            location += f", {country}"

        text = (
            f"{emoji} {location}\n\n"
            f"<b>{condition}</b>\n"
            f"Температура: <b>{temp}°C</b>\n"
            f"Ощущается: <b>{feels}°C</b>\n"
            f"Влажность: <b>{humidity}%</b>\n"
            f"Ветер: <b>{wind} км/ч</b> {_wind_dir(wind_dir)}"
        )
        await safe_edit(message, text, parse_mode=ParseMode.HTML)

    async def _forecast(message, city, log):
        await safe_edit(message, f"Загрузка прогноза: <b>{city}</b>...", parse_mode=ParseMode.HTML)

        loop = asyncio.get_running_loop()
        geo_params = urllib.parse.urlencode({"name": city, "count": 1, "language": "ru", "format": "json"})
        geo_data = await loop.run_in_executor(None, _http_get, f"{GEO_URL}?{geo_params}")

        results = geo_data.get("results")
        if not results:
            await safe_edit(message, f"Город <b>{city}</b> не найден", parse_mode=ParseMode.HTML)
            return

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        found_name = loc.get("name", city)
        region = loc.get("admin1", "")
        country = loc.get("country", "")

        w_params = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 7,
        })
        w_data = await loop.run_in_executor(None, _http_get, f"{WEATHER_URL}?{w_params}")

        daily = w_data.get("daily", {})
        dates = daily.get("time", [])
        codes = daily.get("weather_code", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        wind = daily.get("wind_speed_10m_max", [])
        precip = daily.get("precipitation_probability_max", [])

        if not dates:
            await safe_edit(message, "Нет данных прогноза", parse_mode=ParseMode.HTML)
            return

        location = f"<b>{found_name}</b>"
        if region:
            location += f", {region}"
        if country:
            location += f", {country}"

        lines = [f"Прогноз — {location}\n"]

        for i in range(len(dates)):
            from datetime import datetime as dt
            date = dt.strptime(dates[i], "%Y-%m-%d")
            day_name = DAYS_RU[date.weekday()]
            date_str = date.strftime("%d.%m")

            cond_name, cond_emoji = _wmo(codes[i] if i < len(codes) else 0)
            hi = tmax[i] if i < len(tmax) else "?"
            lo = tmin[i] if i < len(tmin) else "?"
            w = wind[i] if i < len(wind) else "?"
            p = precip[i] if i < len(precip) else 0

            rain_icon = f"umbrella" if p > 50 else ""
            precip_str = f" | 💧{p}%" if p and p > 0 else ""

            lines.append(
                f"<b>{day_name} {date_str}</b>  {cond_emoji} <i>{cond_name}</i>\n"
                f"  🔺 {hi}°  🔻 {lo}°  💨 {w} км/ч{precip_str}"
            )

        text = "\n".join(lines)
        await safe_edit(message, text, parse_mode=ParseMode.HTML)

    client.add_handler(MessageHandler(
        wea_handler,
        cmd("погода"),
    ))


def on_load():
    print("[weather] Loaded. -погода <город> | -погода п <город>")
