from __future__ import annotations

"""Яндекс Музыка — поиск, скачивание треков, тексты песен, чарт и лайки."""

import os
import json
import uuid
import logging
import asyncio
import tempfile
import shutil
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")
BAR_CFG_FILE = os.path.join(SCRIPT_DIR, "bar_settings.json")
OVERLAY_CFG_FILE = os.path.join(SCRIPT_DIR, "overlay_settings.json")

# Overlay options for -ям now card
OVERLAY_OPTIONS = {
    "title": ("\U0001f4d6 Название трека", "показывать название трека на обложке"),
    "artist": ("\U0001f3a4 Исполнитель", "показывать исполнителя на обложке"),
    "gradient": ("\U0001f3a8 Градиент", "тёмный градиент в нижней части обложки"),
}

# Progress bar preset names
BAR_PRESETS = {
    -1: ("\U0001f3b2 Авто", "рандомный пресет для каждого трека"),
    0:  ("\u2728 Neon Glow", "неоновое свечение"),
    1:  ("\U0001f538 Thick Pill", "толстая капсула"),
    2:  ("\u26a1 Dual Layer", "двойной слой"),
    3:  ("\U0001f4e6 Segmented", "сегментированный"),
    4:  ("\u2b24 Dot Marker", "точка-маркер"),
    5:  ("\u2728 Minimal", "минималистичный акцент"),
}

log = logging.getLogger("sandusr.scripts.yandex_music")

_yandex_client = None


# ───────────────────── helpers ─────────────────────

def _get_token() -> str:
    """Read saved Yandex Music token from file."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _save_token(token: str) -> None:
    """Save Yandex Music token to file."""
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token.strip())


def _load_bar_cfg() -> dict:
    """Load progress bar settings from config file."""
    if os.path.exists(BAR_CFG_FILE):
        try:
            with open(BAR_CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"preset": -1}


def _save_bar_cfg(cfg: dict) -> None:
    """Save progress bar settings to config file."""
    with open(BAR_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _get_client():
    """Return existing sync client or create + init a new one."""
    global _yandex_client
    if _yandex_client is not None:
        return _yandex_client
    token = _get_token()
    if not token:
        raise ValueError("Токен не установлен. Используй -ям token <токен>")
    from yandex_music import Client
    _yandex_client = Client(token).init()
    return _yandex_client


def _reset_client() -> None:
    """Drop cached client (e.g. after token change)."""
    global _yandex_client
    _yandex_client = None


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in a thread to avoid blocking the loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _fmt_dur(ms: int | None) -> str:
    """Format milliseconds -> M:SS."""
    if not ms:
        return "\u2014"
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def _cover_url(cover_uri: str | None, size: str = "200x200") -> str:
    """Convert internal cover URI to a full https URL."""
    if not cover_uri:
        return ""
    return f"https://{cover_uri.replace('%%', size)}"


def _track_line(idx: int, track) -> str:
    """Single-line representation of a track for lists."""
    artists = ", ".join(a.name for a in track.artists) if track.artists else "?"
    dur = _fmt_dur(getattr(track, "duration_ms", None))
    return f"<b>{idx}.</b> {track.title} \u2014 {artists} <i>({dur})</i>"


def _clean_filename(name: str) -> str:
    """Remove characters illegal in file names."""
    return "".join(c for c in name if c not in r'\/:*?"<>|')


# ───────────────────── download & send ─────────────────────

async def _download_send(client, message, track):
    """Download a track, send it as audio, clean up temp files."""
    temp_dir = tempfile.mkdtemp()
    try:
        ym = _get_client()
        infos = await _run_sync(ym.tracks_download_info, track.id)
        if not infos:
            await message.edit_text("\u274c Не удалось получить информацию для скачивания")
            return

        best = max(
            [i for i in infos if not i.preview],
            key=lambda x: x.bitrate_in_kbps,
            default=None,
        )
        if not best:
            best = infos[0]

        title = track.title or "track"
        artist = track.artists[0].name if track.artists else "Unknown"
        safe_name = _clean_filename(f"{title} - {artist}")
        filepath = os.path.join(temp_dir, f"{safe_name}.mp3")

        await message.edit_text(f"\u23ec Скачиваю {best.bitrate_in_kbps} kbps\u2026")
        best.download(filepath)

        # fetch cover for thumbnail
        thumb_path = None
        if getattr(track, "cover_uri", None):
            try:
                import urllib.request
                thumb_url = _cover_url(track.cover_uri, "300x300")
                thumb_path = os.path.join(temp_dir, "cover.jpg")
                urllib.request.urlretrieve(thumb_url, thumb_path)
            except Exception:
                pass

        artists_str = ", ".join(a.name for a in track.artists) if track.artists else ""
        duration_s = (track.duration_ms or 0) // 1000

        await message.edit_text("\ud83d\udce4 Отправляю\u2026")

        try:
            await client.send_audio(
                chat_id=message.chat.id,
                audio=filepath,
                title=title,
                performer=artists_str,
                duration=duration_s,
                thumb=thumb_path,
            )
            await message.delete()
        except Exception:
            # fallback to document if audio fails (e.g. size limit)
            try:
                await client.send_document(
                    chat_id=message.chat.id,
                    document=filepath,
                    caption=f"\ud83c\udfb5 {title} \u2014 {artists_str}",
                )
                await message.delete()
            except Exception as e2:
                log.error("send_document failed: %s", e2, exc_info=True)
                await message.edit_text(f"\u274c Не удалось отправить: {e2}")

    except Exception as e:
        log.error("download error: %s", e, exc_info=True)
        await message.edit_text(f"\u274c Ошибка скачивания: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def _download_send_callback(client, callback_query, track):
    """Same as _download_send but triggered from an inline button."""
    await callback_query.answer("\u23ec Скачиваю\u2026")
    temp_dir = tempfile.mkdtemp()
    try:
        ym = _get_client()
        infos = await _run_sync(ym.tracks_download_info, track.id)
        if not infos:
            await callback_query.answer("\u274c Не удалось скачать", show_alert=True)
            return

        best = max(
            [i for i in infos if not i.preview],
            key=lambda x: x.bitrate_in_kbps,
            default=None,
        )
        if not best:
            best = infos[0]

        title = track.title or "track"
        artist = track.artists[0].name if track.artists else "Unknown"
        safe_name = _clean_filename(f"{title} - {artist}")
        filepath = os.path.join(temp_dir, f"{safe_name}.mp3")

        best.download(filepath)

        thumb_path = None
        if getattr(track, "cover_uri", None):
            try:
                import urllib.request
                thumb_url = _cover_url(track.cover_uri, "300x300")
                thumb_path = os.path.join(temp_dir, "cover.jpg")
                urllib.request.urlretrieve(thumb_url, thumb_path)
            except Exception:
                pass

        artists_str = ", ".join(a.name for a in track.artists) if track.artists else ""
        duration_s = (track.duration_ms or 0) // 1000

        msg = callback_query.message
        await client.send_audio(
            chat_id=msg.chat.id,
            audio=filepath,
            title=title,
            performer=artists_str,
            duration=duration_s,
            thumb=thumb_path,
            reply_to_message_id=msg.reply_to_message_id,
        )
    except Exception as e:
        log.error("callback download error: %s", e, exc_info=True)
        await callback_query.answer(f"\u274c {e}", show_alert=True)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ───────────────────── command handlers ─────────────────────

async def _cmd_help(message) -> None:
    """Show help text."""
    from pyrogram.enums import ParseMode

    text = (
        "<b>\ud83c\udfb5 Яндекс Музыка</b>\n\n"
        "<code>-ям s</code> <i>запрос</i> \u2014 поиск треков\n"
        "<code>-ям d</code> <i>id</i> \u2014 скачать/отправить трек\n"
        "<code>-ям l</code> <i>id</i> \u2014 текст песни\n"
        "<code>-ям a</code> <i>запрос</i> \u2014 поиск исполнителя\n"
        "<code>-ям b</code> <i>запрос</i> \u2014 поиск альбома\n"
        "<code>-ям liked</code> \u2014 любимые треки\n"
        "<code>-ям chart</code> \u2014 чарт\n"
        "<code>-ям now</code> \u2014 что сейчас играет\n"
        "<code>-ям bar</code> \u2014 стиль прогресс-бара\n"
        "<code>-ям overlay</code> \u2014 надписи на обложке\n"
        "<code>-ям debug</code> \u2014 диагностика API\n"
        "<code>-ям token</code> <i>токен</i> \u2014 установить токен\n\n"
        "<i>Получить токен: </i>"
        '<a href="https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d">'
        "OAuth авторизация</a>"
    )
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception:
        await message.reply(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def _cmd_search(client, message) -> None:
    """Search tracks by query."""
    from pyrogram.enums import ParseMode
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        try:
            await message.edit_text(
                "\u274c Использование: <code>-ям s запрос</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    query = parts[2]
    try:
        await message.edit_text("\ud83d\udd0d Ищу\u2026")
        ym = _get_client()
        result = await _run_sync(ym.search, query, "track")

        if not result or not result.tracks or not result.tracks.results:
            try:
                await message.edit_text("\u2764\ufe0f Ничего не найдено")
            except Exception:
                pass
            return

        lines = [f"<b>\ud83d\udd0d Результаты: {query}</b>\n"]
        buttons: list[list[InlineKeyboardButton]] = []
        for i, track in enumerate(result.tracks.results[:10], 1):
            lines.append(_track_line(i, track))
            if track.available:
                label = f"\u2b07 {i}. {track.title[:30]}"
                buttons.append([InlineKeyboardButton(label, callback_data=f"ym_dl:{track.id}")])

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

        kw = dict(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if buttons:
            kw["reply_markup"] = InlineKeyboardMarkup(buttons)

        try:
            await message.edit_text(**kw)
        except Exception:
            await message.reply(**kw)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("search error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка поиска: {e}")
        except Exception:
            pass


async def _cmd_download(client, message) -> None:
    """Download and send a track by its ID."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        try:
            await message.edit_text(
                "\u274c Использование: <code>-ям d id_трека</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    track_id = parts[2].strip()
    try:
        ym = _get_client()
        await message.edit_text("\ud83c\udfb5 Загружаю информацию\u2026")
        tracks = await _run_sync(ym.tracks, track_id)
        if not tracks:
            try:
                await message.edit_text("\u274c Трек не найден")
            except Exception:
                pass
            return
        await _download_send(client, message, tracks[0])
    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("download-by-id error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_lyrics(message) -> None:
    """Fetch and display lyrics for a track."""
    from pyrogram.enums import ParseMode

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        try:
            await message.edit_text(
                "\u274c Использование: <code>-ям l id_трека</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    track_id = parts[2].strip()
    try:
        ym = _get_client()
        await message.edit_text("\ud83d\udcdd Загружаю текст\u2026")

        tracks = await _run_sync(ym.tracks, track_id)
        if not tracks:
            try:
                await message.edit_text("\u274c Трек не найден")
            except Exception:
                pass
            return

        track = tracks[0]
        lyrics_data = await _run_sync(ym.tracks_lyrics, track.id, format_="TEXT")

        if not lyrics_data:
            artists = ", ".join(a.name for a in track.artists) if track.artists else ""
            try:
                await message.edit_text(
                    f"\u274c Текст песни недоступен для:\n"
                    f"\ud83c\udfb5 <b>{track.title}</b> \u2014 {artists}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

        # extract plain text from the lyrics object
        lyrics_text = ""
        lyr = getattr(lyrics_data, "lyrics", None)
        if lyr is not None:
            lyrics_text = getattr(lyr, "full_lyrics", None) or getattr(lyr, "text", "") or ""

        if not lyrics_text:
            try:
                await message.edit_text("\u274c Текст песни пуст или недоступен")
            except Exception:
                pass
            return

        artists = ", ".join(a.name for a in track.artists) if track.artists else ""
        header = f"\ud83c\udfb5 <b>{track.title}</b> \u2014 {artists}\n\n"

        full = header + lyrics_text
        if len(full) > 4000:
            full = full[:3900] + "\n\n<i>\u2026обрезано</i>"

        try:
            await message.edit_text(full, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            await message.reply(full, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("lyrics error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_artist(client, message) -> None:
    """Search artist and show info + popular tracks."""
    from pyrogram.enums import ParseMode
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        try:
            await message.edit_text(
                "\u274c Использование: <code>-ям a запрос</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    query = parts[2]
    try:
        await message.edit_text("\ud83c\udfa4 Ищу исполнителя\u2026")
        ym = _get_client()
        result = await _run_sync(ym.search, query, "artist")

        if not result or not result.artists or not result.artists.results:
            try:
                await message.edit_text("\u274c Исполнитель не найден")
            except Exception:
                pass
            return

        artist = result.artists.results[0]
        lines = [f"\ud83c\udfa4 <b>{artist.name}</b>"]

        genres = getattr(artist, "genres", None)
        if genres:
            lines.append(f"\ud83c\udfb5 Жанры: {', '.join(genres)}")

        counts = getattr(artist, "counts", None)
        if counts:
            t = getattr(counts, "tracks", None)
            a = getattr(counts, "albums", None)
            if t:
                lines.append(f"\ud83c\udfb5 Треков: {t}")
            if a:
                lines.append(f"\ud83d\udcbf Альбомов: {a}")

        likes = getattr(artist, "likes_count", None)
        if likes:
            lines.append(f"\u2764\ufe0f Лайков: {likes}")

        desc = getattr(artist, "description", None)
        if desc:
            desc_text = getattr(desc, "text", str(desc))
            if desc_text:
                lines.append(f"\n{desc_text[:800]}")

        buttons: list[list[InlineKeyboardButton]] = []
        pop = getattr(artist, "popular_tracks", None)
        if pop:
            lines.append("\n<b>\ud83d\udd25 Популярные треки:</b>")
            for i, t in enumerate(pop[:5], 1):
                lines.append(_track_line(i, t))
                if t.available:
                    buttons.append(
                        [InlineKeyboardButton(f"\u2b07 {t.title[:35]}", callback_data=f"ym_dl:{t.id}")]
                    )

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

        kw = dict(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if buttons:
            kw["reply_markup"] = InlineKeyboardMarkup(buttons)

        try:
            await message.edit_text(**kw)
        except Exception:
            await message.reply(**kw)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("artist error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_album(client, message) -> None:
    """Search album and show track list."""
    from pyrogram.enums import ParseMode
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        try:
            await message.edit_text(
                "\u274c Использование: <code>-ям b запрос</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    query = parts[2]
    try:
        await message.edit_text("\ud83d\udcbf Ищу альбом\u2026")
        ym = _get_client()
        result = await _run_sync(ym.search, query, "album")

        if not result or not result.albums or not result.albums.results:
            try:
                await message.edit_text("\u274c Альбом не найден")
            except Exception:
                pass
            return

        album_id = result.albums.results[0].id
        album = await _run_sync(ym.albums_with_tracks, album_id)
        if not album:
            try:
                await message.edit_text("\u274c Не удалось загрузить альбом")
            except Exception:
                pass
            return

        artists = ", ".join(a.name for a in album.artists) if album.artists else ""
        header = f"\ud83d\udcbf <b>{album.title}</b>\n\ud83c\udfa4 {artists}"
        if album.year:
            header += f" ({album.year})"
        if album.genre:
            header += f"\n\ud83c\udfb5 {album.genre}"
        if album.track_count:
            header += f"\n\ud83c\udfb5 Треков: {album.track_count}"

        lines = [header, ""]
        buttons: list[list[InlineKeyboardButton]] = []
        for vol_idx, volume in enumerate(album.volumes, 1):
            if len(album.volumes) > 1:
                lines.append(f"<b>Диск {vol_idx}:</b>")
            for i, track in enumerate(volume, 1):
                lines.append(_track_line(i, track))
                if track.available:
                    buttons.append(
                        [InlineKeyboardButton(f"\u2b07 {track.title[:35]}", callback_data=f"ym_dl:{track.id}")]
                    )

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

        kw = dict(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if buttons:
            kw["reply_markup"] = InlineKeyboardMarkup(buttons)

        try:
            await message.edit_text(**kw)
        except Exception:
            await message.reply(**kw)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("album error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_liked(client, message) -> None:
    """Show user's liked tracks."""
    from pyrogram.enums import ParseMode
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        await message.edit_text("\u2764\ufe0f Загружаю любимые треки\u2026")
        ym = _get_client()
        liked = await _run_sync(ym.users_likes_tracks)

        if not liked or not liked.tracks:
            try:
                await message.edit_text("\ud83d\udced Список лайков пуст")
            except Exception:
                pass
            return

        lines = [f"<b>\u2764\ufe0f Любимые треки ({len(liked.tracks)}):</b>\n"]
        buttons: list[list[InlineKeyboardButton]] = []
        for i, ts in enumerate(liked.tracks[:15], 1):
            try:
                track = await _run_sync(ts.fetch_track)
                if track:
                    lines.append(_track_line(i, track))
                    if track.available:
                        buttons.append(
                            [InlineKeyboardButton(
                                f"\u2b07 {track.title[:35]}",
                                callback_data=f"ym_dl:{track.id}",
                            )]
                        )
            except Exception:
                lines.append(f"<b>{i}.</b> [ошибка загрузки]")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

        kw = dict(text=text, parse_mode=ParseMode.HTML)
        if buttons:
            kw["reply_markup"] = InlineKeyboardMarkup(buttons)

        try:
            await message.edit_text(**kw)
        except Exception:
            await message.reply(**kw)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("liked error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_chart(client, message) -> None:
    """Show Yandex Music chart (top tracks)."""
    from pyrogram.enums import ParseMode
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        await message.edit_text("\ud83d\udcca Загружаю чарт\u2026")
        ym = _get_client()
        landing = await _run_sync(ym.landing, ["chart"])

        if not landing or not landing.blocks:
            try:
                await message.edit_text("\u274c Не удалось загрузить чарт")
            except Exception:
                pass
            return

        # find the chart block
        chart_block = None
        for block in landing.blocks:
            bid = getattr(block, "block_id", None)
            if bid == "chart":
                chart_block = block
                break

        if not chart_block:
            try:
                await message.edit_text("\u274c Чарт не найден")
            except Exception:
                pass
            return

        items = getattr(chart_block, "entities", None) or []
        lines = ["<b>\ud83d\udcca Яндекс Музыка Чарт</b>\n"]
        buttons: list[list[InlineKeyboardButton]] = []
        for i, item in enumerate(items[:15], 1):
            track = None
            if hasattr(item, "track") and item.track:
                track = item.track
            elif hasattr(item, "fetch_track"):
                try:
                    track = await _run_sync(item.fetch_track)
                except Exception:
                    continue
            if not track:
                continue
            lines.append(_track_line(i, track))
            if track.available:
                buttons.append(
                    [InlineKeyboardButton(f"\u2b07 {i}. {track.title[:30]}", callback_data=f"ym_dl:{track.id}")]
                )

        if not lines or len(lines) == 1:
            try:
                await message.edit_text("\u274c Чарт пуст")
            except Exception:
                pass
            return

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n<i>\u2026обрезано</i>"

        kw = dict(text=text, parse_mode=ParseMode.HTML)
        if buttons:
            kw["reply_markup"] = InlineKeyboardMarkup(buttons)

        try:
            await message.edit_text(**kw)
        except Exception:
            await message.reply(**kw)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("chart error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


def _generate_now_cover(cover_uri: str, title: str = "", artists: str = "",
                         show_title=True, show_artist=True, show_gradient=True,
                         **kwargs) -> str | None:
    """Generate 400x400 now-playing card with cover + optional text overlay.

    Args:
        show_title:    draw track title text
        show_artist:   draw artist name text
        show_gradient: draw dark gradient at the bottom

    Returns path to the generated image or None on failure.
    """
    import urllib.request
    from PIL import Image, ImageDraw, ImageFont

    try:
        cover_url = _cover_url(cover_uri, "400x400")
        tmp_out = os.path.join(tempfile.gettempdir(), "ym_now_card.png")

        urllib.request.urlretrieve(cover_url, tmp_out)
        img = Image.open(tmp_out).convert("RGBA").resize((400, 400), Image.LANCZOS)

        has_text = (show_title and title) or (show_artist and artists)

        # ── bottom gradient overlay (only if we show text, or forced on) ──
        if show_gradient and has_text:
            overlay = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
            draw_ov = ImageDraw.Draw(overlay)
            for y in range(160, 400):
                alpha = int(180 * ((y - 160) / 240))
                alpha = max(0, min(255, alpha))
                draw_ov.line([(0, y), (400, y)], fill=(0, 0, 0, alpha))
            img = Image.alpha_composite(img, overlay)

        # ── text ──
        if has_text:
            draw = ImageDraw.Draw(img)

            font_candidates = [
                "/usr/share/fonts/truetype/chinese/NotoSansSC[wght].ttf",
                "/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/english/Tinos-Regular.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/tahoma.ttf",
            ]
            font_path = None
            for fp in font_candidates:
                if os.path.exists(fp):
                    font_path = fp
                    break

            try:
                font_title = ImageFont.truetype(font_path, 22)
                font_artist = ImageFont.truetype(font_path, 17)
            except Exception:
                font_title = ImageFont.load_default()
                font_artist = ImageFont.load_default()

            y_base = 290

            if show_title:
                title_text = title or ""
                if len(title_text) > 35:
                    title_text = title_text[:33] + "..."
                draw.text((20, y_base), title_text, fill="white", font=font_title)

            if show_artist:
                artist_text = artists or ""
                if len(artist_text) > 40:
                    artist_text = artist_text[:38] + "..."
                draw.text((20, y_base + 30), artist_text, fill=(220, 220, 220), font=font_artist)

        img.convert("RGB").save(tmp_out, "PNG")
        return tmp_out

    except Exception as e:
        log.error("generate_now_cover error: %s", e, exc_info=True)
        return None


def _fetch_now_playing():
    """Fetch currently playing track. Returns (track, context_type) or (None, None).

    Uses yandex-music 2.2.0 API:
      0. Ynison WebSocket — real-time player state (best)
      1. queues() + queues_items() — v2 API
      2. player_state() — v2 API (direct player status)
      3. feed() → last played / recent (fallback)
      4. landing() → recommendations (fallback)
    """
    # ── Method 0: Ynison WebSocket (real-time player state) ──
    try:
        ynison = _fetch_ynison_state()
        if ynison and ynison.get("track_id"):
            track_id = ynison["track_id"]
            album_id = ynison.get("album_id")
            ym = _get_client()
            try:
                tracks = ym.tracks([str(track_id)])
                if tracks:
                    track = tracks[0]
                    # Attach Ynison metadata for caption
                    track._ynison_paused = ynison.get("paused", True)
                    track._ynison_progress = ynison.get("progress_ms")
                    track._ynison_duration = ynison.get("duration_ms")
                    track._ynison_device = ynison.get("device_name")
                    track._ynison_album_id = album_id
                    log.info("Ynison: got track '%s' via WebSocket", track.title)
                    return track, "ynison"
            except Exception as e:
                log.warning("Ynison: failed to fetch track %s: %s", track_id, e)
    except Exception as e:
        log.warning("Ynison failed: %s", e)

    ym = _get_client()

    # ── Method 1: queues_list() + queue(id) or queues_items() ──
    #   v3: queues_list() → queue(id)
    #   v2: queues() → queues_items(id)
    for q_method in ("queues_list", "queues", "get_queues", "list_queues"):
        if hasattr(ym, q_method):
            try:
                queues = getattr(ym, q_method)()
                if queues:
                    q = queues[0]
                    qid = getattr(q, "id", None)
                    if qid:
                        # v3: queue(id) — возвращает очередь с треками
                        qi_tried = False
                        for qi_method in ("queues_items", "get_queues_items", "queue"):
                            if hasattr(ym, qi_method):
                                try:
                                    queue_data = getattr(ym, qi_method)(qid)
                                    qi_tried = True

                                    # queue() в v3 возвращает объект Queue с .tracks
                                    track_found = None
                                    qt = getattr(queue_data, "tracks", None)
                                    qi = getattr(queue_data, "items", None)
                                    ct = getattr(queue_data, "current_track", None)

                                    # Приоритет: current_track > items[0] > tracks[0]
                                    if ct and hasattr(ct, "title"):
                                        track_found = ct
                                    elif qi:
                                        for first in qi:
                                            t = getattr(first, "track", None)
                                            if t and hasattr(t, "title"):
                                                track_found = t
                                                break
                                            elif hasattr(first, "track_id"):
                                                tid = first.track_id
                                                t = ym.tracks([str(tid)])
                                                if t:
                                                    track_found = t[0]
                                                    break
                                    if not track_found and qt:
                                        for first in qt:
                                            if hasattr(first, "title"):
                                                track_found = first
                                                break
                                            elif hasattr(first, "track_id"):
                                                tid = first.track_id
                                                t = ym.tracks([str(tid)])
                                                if t:
                                                    track_found = t[0]
                                                    break

                                    if track_found:
                                        ctx = getattr(q, "context", None)
                                        ctx_type = getattr(ctx, "type", None) if ctx else None
                                        return track_found, ctx_type or "queue"
                                except Exception as e:
                                    log.debug("%s(%s) failed: %s", qi_method, qid, e)
                        if not qi_tried:
                            log.debug("No queue detail method found")
            except Exception as e:
                log.warning("%s failed: %s", q_method, e)
            break

    # ── Method 2: player_state() (yandex-music 2.x) ──
    for method_name in ("player_state", "player", "player_state_with_context"):
        if hasattr(ym, method_name):
            try:
                result = getattr(ym, method_name)()
                if result:
                    track = getattr(result, "track", None)
                    if not track and hasattr(result, "tracks"):
                        tracks_list = result.tracks
                        if tracks_list:
                            track = tracks_list[0]
                    if track:
                        return track, method_name
            except Exception as e:
                log.debug("%s failed: %s", method_name, e)

    # ── Method 3: feed (last played / recent) ──
    if hasattr(ym, "feed"):
        try:
            feed = ym.feed()
            if feed:
                # feed.generated содержит недавнюю активность
                gen = getattr(feed, "generated", None) or []
                for g in (gen[:5] if gen else []):
                    tracks_data = getattr(g, "tracks", None) or []
                    for td in tracks_data:
                        track = getattr(td, "track", None)
                        if not track and hasattr(td, "fetch_track"):
                            try:
                                track = td.fetch_track()
                            except Exception:
                                pass
                        if track:
                            return track, "last_played"
        except Exception as e:
            log.warning("feed failed: %s", e)

    # ── Method 3: landing blocks ──
    for block_ids in [["recent"], ["personal-recommendations"]]:
        try:
            landing = ym.landing(block_ids)
            if landing and landing.blocks:
                for block in landing.blocks:
                    bid = str(getattr(block, "block_id", ""))
                    entities = getattr(block, "entities", None) or []
                    for ent in entities:
                        track = getattr(ent, "track", None)
                        if not track and hasattr(ent, "fetch_track"):
                            try:
                                track = ent.fetch_track()
                            except Exception:
                                pass
                        if track:
                            return track, bid
        except Exception as e:
            log.debug("landing(%s) failed: %s", block_ids, e)

    return None, None


def _fetch_ynison_state():
    """Connect to Ynison WebSocket and fetch player state.

    Based on working implementations from:
      - FozerG/YandexMusicRPC (ymrpc/yandex_ws.py)
      - vsecoder/hikka_modules (ymnow.py)
      - trudenboy/ma-provider-yandex-ynison

    Two-step WebSocket handshake (raw asyncio, no websockets library):
      1. Connect to redirector → get host, redirect_ticket, session_id
      2. Connect to state service (with ticket in subprotocol header) → receive player state

    Returns dict with:
      - track_id, album_id, playable_id, progress_ms, duration_ms, paused, device_name
    or None on failure.
    """
    import ssl as _ssl
    import hashlib
    import base64

    token = _get_token()
    if not token:
        return None

    device_id = uuid.uuid4().hex[:16]
    # Ynison-Device-Info must be double-encoded JSON string
    device_info_str = json.dumps({"app_name": "Chrome", "type": 1})

    def _build_proto(**extra):
        """Build Sec-WebSocket-Protocol header value.
        Bearer, v2, {"Ynison-Device-Id":"...","Ynison-Device-Info":"{...json...}"}
        """
        proto_obj = {"Ynison-Device-Id": device_id, "Ynison-Device-Info": device_info_str}
        proto_obj.update(extra)
        return "Bearer, v2, " + json.dumps(proto_obj, separators=(",", ":"))

    async def _ws_handshake(host, path, port=443, protocol=None):
        """Perform raw WebSocket handshake, return (reader, writer, leftover)."""
        if not protocol:
            protocol = _build_proto()
        ssl_ctx = _ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_ctx), timeout=10,
        )
        ws_key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Protocol: {protocol}\r\n"
            f"Authorization: OAuth {token}\r\n"
            f"Origin: https://music.yandex.ru\r\n"
            f"\r\n"
        )
        writer.write(request.encode())
        await writer.drain()

        # Read HTTP response, keeping any data after headers (WebSocket frames)
        response_data = b""
        while b"\r\n\r\n" not in response_data:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
            if not chunk:
                break
            response_data += chunk

        header_end = response_data.index(b"\r\n\r\n") + 4
        leftover = response_data[header_end:]  # might contain WS frame data
        response_str = response_data[:header_end].decode("utf-8", errors="replace")

        if "101" not in response_str.split("\r\n")[0]:
            log.warning("Ynison handshake failed: %s", response_str.split("\r\n")[0])
            writer.close()
            return None, None, None

        return reader, writer, leftover

    async def _ws_recv(reader, leftover=b""):
        """Read one WebSocket text frame, using leftover data from handshake."""
        buf = bytearray(leftover)
        while True:
            # Need at least 2 bytes for frame header
            while len(buf) < 2:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
                if not chunk:
                    return None
                buf.extend(chunk)

            opcode = buf[0] & 0x0F
            masked = (buf[1] >> 7) & 1
            length = buf[1] & 0x7F
            header_size = 2

            if length == 126:
                while len(buf) < 4:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
                    if not chunk:
                        return None
                    buf.extend(chunk)
                length = int.from_bytes(buf[2:4], "big")
                header_size = 4
            elif length == 127:
                while len(buf) < 10:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
                    if not chunk:
                        return None
                    buf.extend(chunk)
                length = int.from_bytes(buf[2:10], "big")
                header_size = 10

            mask_size = 4 if masked else 0
            total_header = header_size + mask_size

            while len(buf) < total_header + length:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
                if not chunk:
                    return None
                buf.extend(chunk)

            payload = bytes(buf[total_header:total_header + length])
            if masked:
                mask_key = buf[header_size:total_header]
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            # Consume processed bytes
            del buf[:total_header + length]

            if opcode == 8:  # Close
                return None
            if opcode == 9:  # Ping — skip
                continue
            # opcode 1 (text) or 2 (binary)
            return payload.decode("utf-8", errors="replace")

    async def _ws_send(writer, text):
        """Send one masked WebSocket text frame."""
        data = text.encode("utf-8")
        length = len(data)
        mask_key = b"\xab\xcd\xef\x01"
        if length < 126:
            frame = bytes([0x81, 0x80 | length]) + mask_key
        elif length < 65536:
            frame = bytes([0x81, 0x80 | 126]) + length.to_bytes(2, "big") + mask_key
        else:
            frame = bytes([0x81, 0x80 | 127]) + length.to_bytes(8, "big") + mask_key
        masked_data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        writer.write(frame + masked_data)
        await writer.drain()

    async def _ynison_connect():
        # ── Step 1: Redirector ──
        try:
            reader, writer, leftover = await _ws_handshake(
                "ynison.music.yandex.ru",
                "/redirector.YnisonRedirectService/GetRedirectToYnison",
            )
            if not reader:
                return None
            redirect_msg = await _ws_recv(reader, leftover)
            log.info("Ynison redirector response: %s", redirect_msg[:500] if redirect_msg else "empty")
            writer.close()
        except Exception as e:
            log.warning("Ynison redirector failed: %s", e)
            return None

        if not redirect_msg:
            return None

        # Parse redirector response
        target_host = None
        redirect_ticket = None
        session_id = None

        try:
            data = json.loads(redirect_msg)
            target_host = data.get("host") or data.get("targetHost") or data.get("target_host")
            redirect_ticket = data.get("redirect_ticket") or data.get("ticket")
            session_id = data.get("session_id")
        except (json.JSONDecodeError, TypeError):
            pass

        if not target_host or not redirect_ticket:
            import re
            host_match = re.search(r'"host"\s*:\s*"([^"]+)"', redirect_msg)
            ticket_match = re.search(r'"(?:redirect_)?ticket"\s*:\s*"?([^"\s,}]+)', redirect_msg)
            session_match = re.search(r'"session_id"\s*:\s*(\d+)', redirect_msg)
            if host_match:
                target_host = host_match.group(1)
            if ticket_match:
                redirect_ticket = ticket_match.group(1)
            if session_match:
                session_id = session_match.group(1)

        if not target_host or not redirect_ticket:
            log.warning("Ynison: could not parse redirector response: %s", redirect_msg[:200])
            return None

        log.info("Ynison: host=%s, ticket=%s, session=%s", target_host, redirect_ticket, session_id)

        # ── Step 2: State service (ticket + session_id in subprotocol header) ──
        try:
            extra = {"Ynison-Redirect-Ticket": str(redirect_ticket)}
            if session_id:
                extra["Ynison-Session-Id"] = str(session_id)
            state_proto = _build_proto(**extra)

            reader, writer, leftover = await _ws_handshake(
                target_host,
                "/ynison_state.YnisonStateService/PutYnisonState",
                protocol=state_proto,
            )
            if not reader:
                log.warning("Ynison: state handshake failed")
                return None

            # Shadow/Observer mode — read current state, don't intercept playback
            import random as _rnd
            init_msg = json.dumps({
                "update_full_state": {
                    "player_state": {
                        "player_queue": {
                            "current_playable_index": -1,
                            "entity_id": "",
                            "entity_type": "VARIOUS",
                            "playable_list": [],
                            "options": {"repeat_mode": "NONE"},
                            "entity_context": "BASED_ON_ENTITY_BY_DEFAULT",
                            "version": {
                                "device_id": device_id,
                                "version": int(1e18 * _rnd.random()),
                                "timestamp_ms": 0,
                            },
                            "from_optional": "",
                        },
                        "status": {
                            "duration_ms": 0,
                            "paused": True,
                            "playback_speed": 1,
                            "progress_ms": 0,
                            "version": {
                                "device_id": device_id,
                                "version": int(1e18 * _rnd.random()),
                                "timestamp_ms": 0,
                            },
                        },
                    },
                    "device": {
                        "capabilities": {
                            "can_be_player": True,
                            "can_be_remote_controller": False,
                            "volume_granularity": 16,
                        },
                        "info": {
                            "device_id": device_id,
                            "type": "WEB",
                            "title": "sandusr",
                            "app_name": "sandusr",
                        },
                        "volume_info": {"volume": 0},
                        "is_shadow": True,
                    },
                    "is_currently_active": False,
                },
                "rid": uuid.uuid4().hex,
                "player_action_timestamp_ms": 0,
                "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
            })
            await _ws_send(writer, init_msg)

            response = await _ws_recv(reader, leftover)
            log.info("Ynison state response (%d bytes): %s", len(response) if response else 0, response[:2000] if response else "empty")
            # Save full response to file for debugging
            if response:
                try:
                    debug_dir = os.path.join(SCRIPT_DIR, "logs")
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(os.path.join(debug_dir, "ynison_response.json"), "w", encoding="utf-8") as f:
                        f.write(response)
                    log.info("Ynison: full response saved to logs/ynison_response.json")
                except Exception as e:
                    log.debug("Ynison: failed to save debug file: %s", e)
            writer.close()
            return response

        except Exception as e:
            log.warning("Ynison state service failed: %s", e)
            return None

    # Run async code in new event loop (we're in sync context)
    loop = asyncio.new_event_loop()
    try:
        response = loop.run_until_complete(_ynison_connect())
    finally:
        loop.close()

    if not response:
        return None

    # Parse player state from response
    try:
        data = json.loads(response)
    except (json.JSONDecodeError, TypeError):
        log.warning("Ynison: invalid JSON response")
        return None

    player_state = None
    if isinstance(data, dict):
        # New format: flat update_full_state at top level
        full = data.get("update_full_state")
        if full:
            player_state = full.get("player_state") or full
        # Old/alternative format: wrapped in updates array
        if not player_state:
            updates = data.get("updates", [])
            for u in updates:
                full = u.get("update_full_state", {})
                if full:
                    player_state = full.get("player_state") or full
                    break
        if not player_state:
            player_state = data.get("player_state")

    if not player_state or not isinstance(player_state, dict):
        log.debug("Ynison: no player_state in response")
        return None

    pq = player_state.get("player_queue", {})
    playable_list = pq.get("playable_list", [])
    current_idx = pq.get("current_playable_index", 0)
    entity_id = pq.get("entity_id", "")

    log.info("Ynison: entity_id=%s, type=%s, idx=%d, list_len=%d",
             entity_id, pq.get("entity_type"), current_idx, len(playable_list))

    # Try to extract track_id from playable_list[current_idx] first
    track_id = None
    album_id = None

    if playable_list and 0 <= current_idx < len(playable_list):
        playable = playable_list[current_idx]
        playable_id = playable.get("playable_id", "")

        # Format 1: plain track ID — "141591242" (Моя волна, радио)
        if playable_id and ":" not in playable_id:
            try:
                track_id = int(playable_id)
            except ValueError:
                pass
            # album_id comes from separate field
            album_id_str = playable.get("album_id_optional", "")
            if album_id_str:
                try:
                    album_id = int(album_id_str)
                except ValueError:
                    pass
        else:
            # Format 2: "track:12345:album:67890"
            parts = playable_id.split(":")
            for i, p in enumerate(parts):
                if p == "track" and i + 1 < len(parts):
                    try:
                        track_id = int(parts[i + 1])
                    except ValueError:
                        pass
                if p == "album" and i + 1 < len(parts):
                    try:
                        album_id = int(parts[i + 1])
                    except ValueError:
                        pass

    # Fallback: parse entity_id — "track:135433405" or "2045428801:3"
    if not track_id and entity_id:
        parts = entity_id.split(":")
        # "track:ID" format
        for i, p in enumerate(parts):
            if p == "track" and i + 1 < len(parts):
                try:
                    track_id = int(parts[i + 1])
                except ValueError:
                    pass
            if p == "album" and i + 1 < len(parts):
                try:
                    album_id = int(parts[i + 1])
                except ValueError:
                    pass
        # "playlist_id:track_index" format — can't extract track, skip

    status = player_state.get("status", {})
    progress_ms = status.get("progress_ms")
    duration_ms = status.get("duration_ms")
    paused = status.get("paused", True)

    # Device info
    devices = data.get("devices", []) if isinstance(data, dict) else []
    active_device_id = data.get("active_device_id_optional")
    device_name = None
    for d in devices:
        if d.get("device_id") == active_device_id:
            device_name = d.get("device_name") or d.get("app_name")
            break

    if not track_id:
        log.debug("Ynison: could not extract track_id from playable_id=%s", playable_id)
        return None

    return {
        "playable_id": playable_id,
        "progress_ms": progress_ms,
        "duration_ms": duration_ms,
        "paused": paused,
        "device_name": device_name,
        "track_id": track_id,
        "album_id": album_id,
    }


async def _cmd_bar(client, message) -> None:
    """Set progress bar preset. Usage: -ям bar | -ям bar 1"""
    from pyrogram.enums import ParseMode

    parts = message.text.split()
    arg = parts[2] if len(parts) > 2 else ""

    try:
        cfg = _load_bar_cfg()
        current = cfg.get("preset", -1)

        # ── -ям bar (no arg) → show list ──
        if not arg:
            lines = ["<b>Стиль прогресс-бара</b>\n"]
            for pid, (name, desc) in BAR_PRESETS.items():
                tag = " ✓" if pid == current else ""
                lines.append(f"  {name}  <code>{pid}</code>{tag}")
            lines.append(f"\n<i>Текущий: {BAR_PRESETS[current][0]}</i>")
            await message.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)
            return

        # ── -ям bar N → set preset ──
        try:
            preset = int(arg)
        except ValueError:
            await message.edit_text("❌ Укажи номер. Смотри: <code>-ям bar</code>",
                                    parse_mode=ParseMode.HTML)
            return
        if preset not in BAR_PRESETS:
            await message.edit_text(f"❌ Нет пресета {preset}. Смотри: <code>-ям bar</code>",
                                    parse_mode=ParseMode.HTML)
            return
        cfg["preset"] = preset
        _save_bar_cfg(cfg)
        name = BAR_PRESETS[preset][0]
        await message.edit_text(f"✓ Прогресс-бар: {name}", parse_mode=ParseMode.HTML)
    except Exception as e:
        log.error("_cmd_bar error: %s", e, exc_info=True)
        try:
            await message.reply(f"❌ {e}")
        except Exception:
            pass


# ───────────── overlay helpers ─────────────

def _load_overlay_cfg() -> dict:
    """Load overlay settings: {title: bool, artist: bool, gradient: bool}."""
    if os.path.exists(OVERLAY_CFG_FILE):
        try:
            with open(OVERLAY_CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"title": True, "artist": True, "gradient": True}


def _save_overlay_cfg(cfg: dict) -> None:
    with open(OVERLAY_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


async def _cmd_overlay(client, message) -> None:
    """Toggle overlay elements on -ям now cover card.

    -ям overlay          → show current settings
    -ям overlay off      → remove ALL text (clean cover only)
    -ям overlay on       → restore all defaults
    -ям overlay title    → toggle title
    -ям overlay artist   → toggle artist
    -ям overlay gradient → toggle gradient
    """
    from pyrogram.enums import ParseMode
    from scripts._utils import safe_edit

    parts = message.text.split()
    arg = parts[2] if len(parts) > 2 else ""

    cfg = _load_overlay_cfg()

    try:
        if arg == "":
            # ── show current ──
            lines = ["<b>\U0001f3a8 Настройки обложки (-ям now)</b>\n"]
            for key, (name, desc) in OVERLAY_OPTIONS.items():
                state = cfg.get(key, True)
                icon = "\u2705" if state else "\u274c"
                lines.append(f"  {icon} <code>{key}</code> \u2014 {desc}")
            lines.append(
                f"\n<i>Примеры:</i>\n"
                "  <code>-ям overlay off</code> \u2014 чистая обложка\n"
                "  <code>-ям overlay on</code> \u2014 всё по умолчанию\n"
                "  <code>-ям overlay title</code> \u2014 вкл/выкл название\n"
                "  <code>-ям overlay artist</code> \u2014 вкл/выкл исполнителя\n"
                "  <code>-ям overlay gradient</code> \u2014 вкл/выкл градиент"
            )
            await safe_edit(message, "\n".join(lines), parse_mode=ParseMode.HTML)
            return

        if arg == "off":
            cfg = {"title": False, "artist": False, "gradient": False}
            _save_overlay_cfg(cfg)
            await safe_edit(
                message,
                "\u274c Все надписи выключены \u2014 чистая обложка",
                parse_mode=ParseMode.HTML,
            )
            return

        if arg == "on":
            cfg = {"title": True, "artist": True, "gradient": True}
            _save_overlay_cfg(cfg)
            await safe_edit(
                message,
                "\u2705 Все надписи включены",
                parse_mode=ParseMode.HTML,
            )
            return

        # Toggle individual element
        if arg in OVERLAY_OPTIONS:
            cfg[arg] = not cfg.get(arg, True)
            _save_overlay_cfg(cfg)
            state = cfg[arg]
            icon = "\u2705" if state else "\u274c"
            action = "включён" if state else "выключен"
            name = OVERLAY_OPTIONS[arg][0]
            await safe_edit(
                message,
                f"{icon} {name}: {action}",
                parse_mode=ParseMode.HTML,
            )
            return

        # Unknown arg
        valid = ", ".join(f"<code>{k}</code>" for k in OVERLAY_OPTIONS)
        await safe_edit(
            message,
            f"\u274c Неизвестный параметр: <code>{arg}</code>\n"
            f"Доступные: {valid}, <code>on</code>, <code>off</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.error("_cmd_overlay error: %s", e, exc_info=True)
        try:
            await safe_edit(message, f"\u274c Ошибка: {e}", parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def _cmd_now(client, message) -> None:
    """Show currently playing track from Yandex Music with cover card."""
    from pyrogram.enums import ParseMode

    async def _safe(text, **kw):
        """edit_text with reply fallback for groups."""
        try:
            return await message.edit_text(text, **kw)
        except Exception:
            try:
                return await message.reply(text, quote=False, **kw)
            except Exception:
                pass
        return None

    try:
        await _safe("\u270f\ufe0f Определяю\u2026")

        track, ctx_type = await _run_sync(_fetch_now_playing)

        if not track:
            ym_ver = "?.?"
            available = []
            queues_info = ""
            try:
                import yandex_music
                ym_ver = getattr(yandex_music, "__version__", "?")
                ym = _get_client()
                for m in ("queues_list", "queues", "queues_items", "queue", "player_state", "player", "feed", "landing"):
                    if hasattr(ym, m):
                        available.append(m)

                ql = None
                for qm in ("queues_list", "queues", "get_queues", "list_queues"):
                    if hasattr(ym, qm):
                        try:
                            ql = getattr(ym, qm)()
                        except Exception:
                            pass
                        break
                if ql:
                    queues_info = f"\u041e\u0447\u0435\u0440\u0435\u0439 \u043d\u0430\u0439\u0434\u0435\u043d\u043e: {len(ql)}\n"
                    for qi, q in enumerate(ql[:3]):
                        qid = getattr(q, "id", "?")
                        qctx = getattr(q, "context", None)
                        qtype = getattr(qctx, "type", "?") if qctx else "?"
                        queues_info += f"  [{qi}] id={qid}, context={qtype}\n"
                else:
                    queues_info = "\u041e\u0447\u0435\u0440\u0435\u0434\u0438: \u043f\u0443\u0441\u0442\u043e \u0438\u043b\u0438 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b"
            except Exception:
                pass

            await _safe(
                f"\ud83d\udced \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u0438\u0433\u0440\u0430\u044e\u0449\u0438\u0439 \u0442\u0440\u0435\u043a\n\n"
                f"<i>\u0412\u043e\u0437\u043c\u043e\u0436\u043d\u044b\u0435 \u043f\u0440\u0438\u0447\u0438\u043d\u044b:</i>\n"
                f"\u2022 \u041c\u0443\u0437\u044b\u043a\u0430 \u0438\u0433\u0440\u0430\u0435\u0442 \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435 \u2014 \u043e\u0447\u0435\u0440\u0435\u0434\u044c \u043d\u0435 \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u0443\u0435\u0442\u0441\u044f\n"
                f"  (\u043d\u0443\u0436\u0435\u043d \u0434\u0435\u0441\u043a\u0442\u043e\u043f/\u043c\u043e\u0431\u0438\u043b\u044c\u043d\u044b\u0439 \u043a\u043b\u0438\u0435\u043d\u0442 \u042f\u041c)\n"
                f"\u2022 \u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043e\u0447\u0435\u0440\u0435\u0434\u0438 \u0432\u043e\u0441\u043f\u0440\u043e\u0438\u0437\u0432\u0435\u0434\u0435\u043d\u0438\u044f\n\n"
                f"<b>\u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430:</b>\n"
                f"<i>\u0412\u0435\u0440\u0441\u0438\u044f yandex-music: {ym_ver}</i>\n"
                f"<i>\u041c\u0435\u0442\u043e\u0434\u044b: {', '.join(available) if available else 'none'}</i>\n"
                f"<i>{queues_info}</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        artists = ", ".join(a.name for a in track.artists) if track.artists else ""
        artists_plain = artists
        album = track.albums[0].title if track.albums else ""

        # Ynison device
        ynison_device = getattr(track, "_ynison_device", None)

        # Artist link (first artist)
        artist_url = ""
        if track.artists:
            first = track.artists[0]
            aid = getattr(first, "id", None)
            if aid:
                artist_url = f"https://music.yandex.ru/artist/{aid}"

        # Track link
        track_url = f"https://music.yandex.ru/track/{track.id}" if track.id else ""

        # Generate cover card (read overlay settings)
        cover_uri = getattr(track, "cover_uri", None)
        cover_path = None
        if cover_uri:
            ol_cfg = _load_overlay_cfg()
            cover_path = await _run_sync(
                _generate_now_cover, cover_uri,
                title=track.title or "",
                artists=artists_plain,
                show_title=ol_cfg.get("title", True),
                show_artist=ol_cfg.get("artist", True),
                show_gradient=ol_cfg.get("gradient", True),
            )

        # build caption
        caption_lines = []
        if artist_url:
            caption_lines.append(f"\U0001f3a7 <a href=\"{artist_url}\">{artists_plain}</a> \u2014 {track.title}")
        else:
            caption_lines.append(f"\U0001f3a7 {artists_plain} \u2014 {track.title}")
        if ynison_device:
            caption_lines.append(f"\U0001f4f1 {ynison_device}")
        if track_url:
            caption_lines.append(f'\U0001f3a7 <a href="{track_url}">\u042f\u043d\u0434\u0435\u043a\u0441 \u041c\u0443\u0437\u044b\u043a\u0430</a>')
        text = "\n".join(caption_lines)

        await _safe("\U0001f4e1 \u041e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u2026")

        if cover_path and os.path.exists(cover_path):
            try:
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=cover_path,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
                try:
                    await message.delete()
                except Exception:
                    pass
            except Exception:
                await _safe(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        else:
            await _safe(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    except ValueError as e:
        await _safe(f"\u274c {e}", parse_mode=ParseMode.HTML)
    except Exception as e:
        log.error("now error: %s", e, exc_info=True)
        await _safe(f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}", parse_mode=ParseMode.HTML)


async def _cmd_debug(message) -> None:
    """Show diagnostic info about yandex-music client."""
    from pyrogram.enums import ParseMode

    try:
        ym = _get_client()
        methods = sorted([m for m in dir(ym) if not m.startswith("_") and callable(getattr(ym, m, None))])

        # group relevant methods
        queue_methods = [m for m in methods if "queue" in m.lower()]
        player_methods = [m for m in methods if "player" in m.lower() or "play" in m.lower()]
        track_methods = [m for m in methods if "track" in m.lower()]
        feed_methods = [m for m in methods if "feed" in m.lower()]

        import yandex_music
        ver = getattr(yandex_music, "__version__", "?")

        lines = [f"<b>🔧 Yandex Music Debug</b>\n"]
        lines.append(f"Версия библиотеки: <code>{ver}</code>")
        lines.append(f"Всего методов: {len(methods)}\n")

        if queue_methods:
            lines.append(f"<b>Queue ({len(queue_methods)}):</b>\n<code>{', '.join(queue_methods)}</code>")
        if player_methods:
            lines.append(f"\n<b>Player ({len(player_methods)}):</b>\n<code>{', '.join(player_methods)}</code>")
        if track_methods:
            lines.append(f"\n<b>Track ({len(track_methods[:15])}):</b>\n<code>{', '.join(track_methods[:15])}</code>")
        if feed_methods:
            lines.append(f"\n<b>Feed ({len(feed_methods)}):</b>\n<code>{', '.join(feed_methods)}</code>")

        # test feed
        if hasattr(ym, "feed"):
            try:
                feed = await _run_sync(ym.feed)
                if feed:
                    gen = getattr(feed, "generated", None) or []
                    total_tracks = 0
                    for g in gen[:3]:
                        td = getattr(g, "tracks", None) or []
                        total_tracks += len(td)
                    lines.append(f"\n<b>Feed test:</b> {len(gen)} блоков, {total_tracks} треков в первых 3")
            except Exception as e:
                lines.append(f"\n<b>Feed test:</b> ❌ {e}")

        # test queues
        ql_method = None
        for qm in ("queues_list", "queues", "get_queues", "list_queues"):
            if hasattr(ym, qm):
                ql_method = qm
                break
        if ql_method:
            try:
                queues = await _run_sync(getattr(ym, ql_method))
                if queues:
                    lines.append(f"\n<b>Queues ({len(queues)}):</b>")
                    for qi, q in enumerate(queues[:5]):
                        qid = getattr(q, "id", "?")
                        qctx = getattr(q, "context", None)
                        qtype = getattr(qctx, "type", "?") if qctx else "?"
                        lines.append(f"  [{qi}] id={qid}, ctx={qtype}")

                    # пробуем queue() или queues_items() для первой очереди
                    first_qid = getattr(queues[0], "id", None)
                    if first_qid:
                        for qi_method in ("queues_items", "get_queues_items", "queue"):
                            if hasattr(ym, qi_method):
                                try:
                                    qd = await _run_sync(getattr(ym, qi_method), first_qid)
                                    if qd:
                                        attrs = sorted([a for a in dir(qd) if not a.startswith("_")])
                                        lines.append(f"\n<b>{qi_method}() attrs:</b> <code>{', '.join(attrs[:20])}</code>")
                                        for attr in ("track", "current_track", "tracks", "items"):
                                            val = getattr(qd, attr, None)
                                            if val:
                                                if isinstance(val, list):
                                                    lines.append(f"  {attr}: list[{len(val)}]")
                                                    if val:
                                                        item0 = val[0]
                                                        lines.append(f"    [0] type={type(item0).__name__}, attrs={sorted([a for a in dir(item0) if not a.startswith('_')])[:10]}")
                                                else:
                                                    lines.append(f"  {attr}: {type(val).__name__}")
                                except Exception as e:
                                    lines.append(f"\n<b>{qi_method}():</b> ❌ {e}")
                                break
                else:
                    lines.append(f"\n<b>Queues:</b> пусто (music playing?)")
            except Exception as e:
                lines.append(f"\n<b>Queues test:</b> ❌ {e}")
        else:
            lines.append(f"\n<b>Queues:</b> метод не найден")

        # test player_state (v2 API)
        for ps_method in ("player_state", "player"):
            if hasattr(ym, ps_method):
                try:
                    ps = await _run_sync(getattr(ym, ps_method))
                    if ps:
                        ps_track = getattr(ps, "track", None)
                        lines.append(f"\n<b>{ps_method}:</b> ✅ track={'есть' if ps_track else 'нет'}")
                        if not ps_track and hasattr(ps, "tracks"):
                            lines.append(f"  tracks: list[{len(ps.tracks)}]")
                    else:
                        lines.append(f"\n<b>{ps_method}:</b> пусто")
                except Exception as e:
                    lines.append(f"\n<b>{ps_method}:</b> ❌ {e}")
                break

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n<i>...обрезано</i>"

        try:
            await message.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            await message.reply(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("debug error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_token(message) -> None:
    """Set (or update) the Yandex Music OAuth token."""
    from pyrogram.enums import ParseMode

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        try:
            await message.edit_text(
                "\u274c Использование: <code>-ям token YOUR_TOKEN</code>\n\n"
                '<i>Получить токен: </i>'
                '<a href="https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d">'
                "OAuth авторизация</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        return

    token = parts[2].strip()
    try:
        _reset_client()
        _save_token(token)
        ym = _get_client()
        login = ym.me.account.login
        try:
            await message.edit_text(
                f"\u2705 Токен установлен!\n\ud83d\udc64 Аккаунт: <b>{login}</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    except Exception as e:
        _reset_client()
        log.error("token error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Неверный токен: {e}", parse_mode=ParseMode.HTML)
        except Exception:
            pass


# ───────────────────── main dispatcher ─────────────────────

def register(client):
    """Called by the loader with the Pyrofork Client. Register handlers."""
    import logging
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler, CallbackQueryHandler
    from pyrogram.types import Message
    from scripts._utils import safe_edit, cmd

    log = logging.getLogger("sandusr.scripts.yandex_music")

    async def _dispatcher(client, message: Message):
        """Single entry point: -ям [sub-command] [args...]"""
        parts = message.text.split()
        sub = parts[1] if len(parts) > 1 else ""

        try:
            if sub in ("s", "search"):
                await _cmd_search(client, message)
            elif sub in ("d", "dl", "download"):
                await _cmd_download(client, message)
            elif sub in ("l", "lyrics", "lyric"):
                await _cmd_lyrics(message)
            elif sub in ("a", "artist"):
                await _cmd_artist(client, message)
            elif sub in ("b", "album"):
                await _cmd_album(client, message)
            elif sub in ("liked", "likes", "like"):
                await _cmd_liked(client, message)
            elif sub in ("chart", "top"):
                await _cmd_chart(client, message)
            elif sub in ("now", "np", "playing"):
                await _cmd_now(client, message)
            elif sub in ("bar", "bars", "progressbar"):
                await _cmd_bar(client, message)
            elif sub in ("overlay", "style", "cover"):
                await _cmd_overlay(client, message)
            elif sub == "debug":
                await _cmd_debug(message)
            elif sub == "token":
                await _cmd_token(message)
            else:
                await _cmd_help(message)
        except Exception as e:
            log.error("unhandled error: %s", e, exc_info=True)
            await safe_edit(message, f"\u274c Неожиданная ошибка: {e}")

    async def _on_callback(client, callback_query):
        """Handle inline button presses (ym_dl:track_id)."""
        data = callback_query.data
        if not data or not data.startswith("ym_dl:"):
            return

        track_id = data.split(":", 1)[1]
        try:
            ym = _get_client()
            tracks = await _run_sync(ym.tracks, track_id)
            if not tracks:
                await callback_query.answer("\u274c Трек не найден", show_alert=True)
                return
            await _download_send_callback(client, callback_query, tracks[0])
        except ValueError as e:
            await callback_query.answer(str(e), show_alert=True)
        except Exception as e:
            log.error("callback error: %s", e, exc_info=True)
            await callback_query.answer(f"\u274c {e}", show_alert=True)

    client.add_handler(MessageHandler(
        _dispatcher,
        cmd("ям"),
    ))

    client.add_handler(CallbackQueryHandler(
        _on_callback,
        filters.regex(r"^ym_dl:"),
    ))


def on_load():
    token = _get_token()
    if token:
        print(f"[yandex_music] Loaded (token: {'*' * 8}...{token[-4:]})")
    else:
        print("[yandex_music] Loaded (токен не установлен)")


def on_unload():
    _reset_client()
    print("[yandex_music] Unloaded")
