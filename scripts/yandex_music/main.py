from __future__ import annotations

"""Яндекс Музыка — поиск, скачивание треков, тексты песен, чарт и лайки."""

import os
import json
import logging
import asyncio
import tempfile
import shutil
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")

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


def _get_client():
    """Return existing sync client or create + init a new one."""
    global _yandex_client
    if _yandex_client is not None:
        return _yandex_client
    token = _get_token()
    if not token:
        raise ValueError("Токен не установлен. Используй .ya token <токен>")
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
        "<code>.ya s</code> <i>запрос</i> \u2014 поиск треков\n"
        "<code>.ya d</code> <i>id</i> \u2014 скачать/отправить трек\n"
        "<code>.ya l</code> <i>id</i> \u2014 текст песни\n"
        "<code>.ya a</code> <i>запрос</i> \u2014 поиск исполнителя\n"
        "<code>.ya b</code> <i>запрос</i> \u2014 поиск альбома\n"
        "<code>.ya liked</code> \u2014 любимые треки\n"
        "<code>.ya chart</code> \u2014 чарт\n"
        "<code>.ya now</code> \u2014 что сейчас играет\n"
        "<code>.ya debug</code> \u2014 диагностика API\n"
        "<code>.ya token</code> <i>токен</i> \u2014 установить токен\n\n"
        "<i>Получить токен (с доступом к очередям): </i>\n"
        '<a href="https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d&scope=play-listen">'
        "OAuth (play-listen)</a>"
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
                "\u274c Использование: <code>.ya s запрос</code>",
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
                "\u274c Использование: <code>.ya d id_трека</code>",
                parse_mode="HTML",
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
                "\u274c Использование: <code>.ya l id_трека</code>",
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
                "\u274c Использование: <code>.ya a запрос</code>",
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
                "\u274c Использование: <code>.ya b запрос</code>",
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


async def _generate_now_cover(cover_uri: str) -> str | None:
    """Generate 500x200 now-playing card: blurred bg + sharp centered cover.

    Returns path to the generated image or None on failure.
    """
    import urllib.request
    from PIL import Image, ImageFilter

    try:
        cover_url = _cover_url(cover_uri, "400x400")
        tmp_cover = os.path.join(tempfile.gettempdir(), "ym_cover_raw.jpg")
        tmp_out = os.path.join(tempfile.gettempdir(), "ym_now_card.png")

        urllib.request.urlretrieve(cover_url, tmp_cover)
        src = Image.open(tmp_cover).convert("RGB")

        # ── blurred background: cover-to-fill 500x200 ──
        bg = src.copy()
        bg = bg.resize((500, 200), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(25))

        # darken overlay so text pops
        overlay = Image.new("RGBA", (500, 200), (0, 0, 0, 120))
        bg_rgba = bg.convert("RGBA")
        bg_rgba = Image.alpha_composite(bg_rgba, overlay)

        # ── sharp centered cover (140x140) ──
        thumb = src.copy()
        thumb = thumb.resize((140, 140), Image.LANCZOS)
        # rounded corners via mask
        mask = Image.new("L", (140, 140), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, 139, 139], radius=12, fill=255)
        thumb = thumb.convert("RGBA")
        thumb.putalpha(mask)

        # paste centered (vertically centered: (200-140)/2 = 30)
        paste_x = (500 - 140) // 2
        paste_y = (200 - 140) // 2
        bg_rgba.paste(thumb, (paste_x, paste_y), thumb)

        bg_rgba.convert("RGB").save(tmp_out, "PNG")
        return tmp_out

    except Exception as e:
        log.error("generate_now_cover error: %s", e, exc_info=True)
        return None


def _fetch_now_playing():
    """Fetch currently playing track. Returns (track, context_type) or (None, None).

    Uses yandex-music 3.x API:
      1. queues_list() → list of Queue objects
      2. queue(queue_id) → full queue with track IDs
      3. feed() → last played / recent (fallback)
      4. landing() → recommendations (fallback)
    """
    ym = _get_client()

    # ── Method 1: queues_list + queue (yandex-music 3.x) ──
    # queues_list() возвращает список Queue объектов с id и текущим треком
    ql_method = None
    for candidate in ("queues_list", "queuesList", "queues"):
        if hasattr(ym, candidate):
            ql_method = candidate
            break

    if ql_method:
        try:
            queues = getattr(ym, ql_method)()
            if queues:
                for q in queues:
                    qid = getattr(q, "id", None)
                    if not qid:
                        continue

                    # queue() возвращает полную очередь с треками
                    q_method = None
                    for qm in ("queue", "get_queue"):
                        if hasattr(ym, qm):
                            q_method = qm
                            break

                    if not q_method:
                        log.debug("no queue() method available")
                        break

                    queue_data = getattr(ym, q_method)(qid)
                    if not queue_data:
                        continue

                    # ищем текущий трек из очереди
                    # атрибут может быть track / current_track / tracks
                    track = getattr(queue_data, "track", None)
                    if not track:
                        track = getattr(queue_data, "current_track", None)

                    # если нет прямого track — пробуем из списка tracks
                    if not track:
                        items = getattr(queue_data, "tracks", None) or getattr(queue_data, "items", None)
                        if items:
                            for item in items:
                                # каждый item может быть Track или QueueItem
                                t = None
                                if hasattr(item, "track"):
                                    t = item.track
                                elif hasattr(item, "track_id"):
                                    tid = item.track_id
                                    if isinstance(tid, int):
                                        ts = ym.tracks([str(tid)])
                                        if ts:
                                            t = ts[0]
                                    elif isinstance(tid, str):
                                        ts = ym.tracks(tid)
                                        if ts:
                                            t = ts[0]
                                else:
                                    t = item  # сам item — это Track
                                if t:
                                    track = t
                                    break

                    if track:
                        ctx = getattr(queue_data, "context", None) or getattr(q, "context", None)
                        ctx_type = getattr(ctx, "type", None) if ctx else None
                        return track, ctx_type or "queue"

                    log.debug("queue(%s) returned no track", qid)

        except Exception as e:
            log.warning("queue method failed: %s", e, exc_info=True)

    # ── Method 2: feed (last played / recent) ──
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


async def _cmd_now(client, message) -> None:
    """Show currently playing track from Yandex Music with cover card."""
    from pyrogram.enums import ParseMode

    try:
        await message.edit_text("🎧 Определяю…")

        track, ctx_type = await _run_sync(_fetch_now_playing)

        if not track:
            # диагностика
            ym_ver = "?.?"
            available = []
            queues_info = ""
            try:
                import yandex_music
                ym_ver = getattr(yandex_music, "__version__", "?")
                ym = _get_client()
                for m in ("queues_list", "queuesList", "queues", "queue", "feed", "landing"):
                    if hasattr(ym, m):
                        available.append(m)

                # попробуем получить список очередей для диагностики
                ql = None
                for qm in ("queues_list", "queuesList", "queues"):
                    if hasattr(ym, qm):
                        try:
                            ql = getattr(ym, qm)()
                        except Exception:
                            pass
                        break
                if ql:
                    queues_info = f"Очередей найдено: {len(ql)}\n"
                    for qi, q in enumerate(ql[:3]):
                        qid = getattr(q, "id", "?")
                        qctx = getattr(q, "context", None)
                        qtype = getattr(qctx, "type", "?") if qctx else "?"
                        queues_info += f"  [{qi}] id={qid}, context={qtype}\n"
                else:
                    queues_info = "Очереди: пусто или недоступны"
            except Exception:
                pass

            await message.edit_text(
                f"📭 Не удалось определить играющий трек\n\n"
                f"<i>Возможные причины:</i>\n"
                f"• Музыка играет в браузере — очередь не синхронизируется\n"
                f"  (нужен десктоп/мобильный клиент ЯМ)\n"
                f"• Нет активной очереди воспроизведения\n\n"
                f"<b>Диагностика:</b>\n"
                f"<i>Версия yandex-music: {ym_ver}</i>\n"
                f"<i>Методы: {', '.join(available) if available else 'none'}</i>\n"
                f"<i>{queues_info}</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        artists = ", ".join(a.name for a in track.artists) if track.artists else ""
        dur = _fmt_dur(getattr(track, "duration_ms", None))
        album = track.albums[0].title if track.albums else ""

        cover_uri = getattr(track, "cover_uri", None)
        cover_path = None
        if cover_uri:
            cover_path = await _run_sync(_generate_now_cover, cover_uri)

        # ── build caption ──
        is_last = ctx_type == "last_played"
        label = "Последний трек:" if is_last else "Сейчас играет:"
        lines = [f"☞ <b>{label}</b>", ""]
        lines.append(f"🎵 <b>{track.title}</b>")
        lines.append(f"🎤 {artists}")
        if album:
            lines.append(f"💿 {album}")
        lines.append(f"⏱ {dur}")
        text = "\n".join(lines)

        await message.edit_text("📡 Отправляю…")

        if cover_path and os.path.exists(cover_path):
            try:
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=cover_path,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
                await message.delete()
            except Exception:
                try:
                    await message.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    pass
        else:
            try:
                await message.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception:
                pass

    except ValueError as e:
        try:
            await message.edit_text(f"\u274c {e}")
        except Exception:
            pass
    except Exception as e:
        log.error("now error: %s", e, exc_info=True)
        try:
            await message.edit_text(f"\u274c Ошибка: {e}")
        except Exception:
            pass


async def _cmd_debug(message) -> None:
    """Show diagnostic info about yandex-music client."""
    from pyrogram.enums import ParseMode

    try:
        ym = _get_client()
        import yandex_music
        ver = getattr(yandex_music, "__version__", "?")

        lines = [f"<b>🔧 Yandex Music Debug</b>\nВерсия: <code>{ver}</code>\n"]

        # ── 1. Аккаунт ──
        try:
            me = ym.me
            if me:
                uid = getattr(me, "uid", None) or getattr(me, "id", None) or "?"
                login = getattr(me.account, "login", "?") if hasattr(me, "account") else "?"
                lines.append(f"<b>▶ Аккаунт:</b> uid={uid}, login={login}")
                # покажем атрибуты me
                me_attrs = sorted([a for a in dir(me) if not a.startswith("_") and not callable(getattr(me, a, None))])
                lines.append(f"  me attrs: <code>{', '.join(me_attrs[:15])}</code>")
                # проверим _request
                req = getattr(ym, "_request", None) or getattr(ym, "request", None)
                if req:
                    lines.append(f"  request type: <code>{type(req).__name__}</code>")
                    base = getattr(req, "base_url", None) or getattr(req, "_base_url", None)
                    if base:
                        lines.append(f"  base_url: <code>{base}</code>")
        except Exception as e:
            lines.append(f"<b>▶ Аккаунт:</b> ❌ {e}")

        # ── 2. Raw API calls (прямой HTTP через requests) ──
        lines.append("")
        try:
            import requests as http_lib
            token = _get_token()
            base = "https://api.music.yandex.net"
            headers = {"Authorization": f"OAuth {token}"}
            for endpoint in ("/queues", "/player/state", "/feed"):
                try:
                    resp = await _run_sync(http_lib.get, f"{base}{endpoint}", headers=headers, timeout=5)
                    data = resp.json() if resp.status_code == 200 else {"error": resp.status_code}
                    if isinstance(data, dict):
                        preview = json.dumps(data, ensure_ascii=False)[:250]
                        lines.append(f"<b>▶ GET {endpoint}:</b> {resp.status_code}\n  <code>{preview}</code>")
                    elif isinstance(data, list):
                        lines.append(f"<b>▶ GET {endpoint}:</b> {resp.status_code}, list[{len(data)}]")
                    else:
                        lines.append(f"<b>▶ GET {endpoint}:</b> {resp.status_code}")
                except Exception as e:
                    lines.append(f"<b>▶ GET {endpoint}:</b> ❌ {type(e).__name__}: {str(e)[:80]}")
        except ImportError:
            lines.append("<b>▶ Raw API:</b> requests не установлен")
        except Exception as e:
            lines.append(f"<b>▶ Raw API:</b> ❌ {e}")

        # ── 3. queues_list через библиотеку ──
        lines.append("")
        ql_method = None
        for qm in ("queues_list", "queuesList", "queues"):
            if hasattr(ym, qm):
                ql_method = qm
                break
        if ql_method:
            try:
                queues = await _run_sync(getattr(ym, ql_method))
                if queues:
                    lines.append(f"<b>▶ {ql_method}:</b> {len(queues)} очередей")
                else:
                    lines.append(f"<b>▶ {ql_method}:</b> пусто")
            except Exception as e:
                lines.append(f"<b>▶ {ql_method}:</b> ❌ {e}")
        else:
            lines.append(f"<b>▶ {ql_method}:</b> не найден")

        # ── 4. feed ──
        if hasattr(ym, "feed"):
            try:
                feed = await _run_sync(ym.feed)
                if feed:
                    gen = getattr(feed, "generated", None) or []
                    lines.append(f"<b>▶ Feed:</b> {len(gen)} блоков")
                else:
                    lines.append(f"<b>▶ Feed:</b> None")
            except Exception as e:
                lines.append(f"<b>▶ Feed:</b> ❌ {e}")

        # ── 5. Вывод ──
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
                "\u274c Использование: <code>.ya token YOUR_TOKEN</code>\n\n"
                '<i>Получить токен (с доступом к очередям):</i>\n'
                '<a href="https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d&scope=play-listen">'
                "OAuth (play-listen)</a>\n\n"
                "<i>Без очередей (только базовый):</i>\n"
                '<a href="https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d">'
                "OAuth (basic)</a>",
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
    from scripts._utils import safe_edit

    log = logging.getLogger("sandusr.scripts.yandex_music")

    async def _dispatcher(client, message: Message):
        """Single entry point: .ya [sub-command] [args...]"""
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
        filters.command("ya", prefixes=".") & filters.me,
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
