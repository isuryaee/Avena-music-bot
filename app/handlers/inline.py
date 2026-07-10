import asyncio
from collections import defaultdict
import logging
import os
import secrets
import time
from aiogram import Router, Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle, InputMediaAudio,
    InputTextMessageContent, ChosenInlineResult, FSInputFile, URLInputFile
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Music
from app.utils.bot_data import BotData
from app.keyboards.inline import Inlines
from app.config import config
from app.utils.helpers import HandlersHelper

logger = logging.getLogger(__name__)

router = Router()

last_query_time = defaultdict(float)
pending_tasks = {}
DEBOUNCE_TIME = 0.5

# Per-song lock to prevent duplicate concurrent downloads
_download_locks: dict[str, asyncio.Lock] = {}


def _song_lock(song_id: str) -> asyncio.Lock:
    if song_id not in _download_locks:
        _download_locks[song_id] = asyncio.Lock()
    return _download_locks[song_id]


async def _edit_inline(bot: Bot, inline_message_id: str, text: str, markup):
    """Edit the inline chat message; silently ignore errors (message may be deleted)."""
    try:
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception as exc:
        logger.debug("Could not edit inline message: %s", exc)


async def _edit_inline_error(bot: Bot, inline_message_id: str, text: str, markup):
    """Report an error/instruction on the inline message. The message is usually audio
    (caption edit), but may still be text if it never became media — fall back accordingly."""
    try:
        await bot.edit_message_caption(
            inline_message_id=inline_message_id,
            caption=text,
            reply_markup=markup,
        )
        return
    except Exception as exc:
        logger.debug("Could not edit inline caption, trying text: %s", exc)

    await _edit_inline(bot, inline_message_id, text, markup)


@router.inline_query()
async def inline_query_handler(query: InlineQuery, bot_data: BotData, db: AsyncSession):
    text = query.query.strip()
    user_id = query.from_user.id
    inlines = Inlines(bot_data.texts)

    if not text:
        return await query.answer(
            [InlineQueryResultArticle(
                id=secrets.token_hex(8),
                title=bot_data.texts.inline_query_empty,
                input_message_content=InputTextMessageContent(
                    message_text=bot_data.texts.inline_query_empty_send
                ),
                reply_markup=inlines.music_lyrics(None, only_switch=True)
            )],
            cache_time=0
        )

    current_time = time.time()
    last_query_time[user_id] = current_time

    if user_id in pending_tasks:
        pending_tasks[user_id].cancel()

    async def delayed_execution(expected_time):
        await asyncio.sleep(DEBOUNCE_TIME)
        if last_query_time[user_id] == expected_time:
            await HandlersHelper.process_query(query, bot_data, db)
        pending_tasks.pop(user_id, None)

    pending_tasks[user_id] = asyncio.create_task(delayed_execution(current_time))


@router.chosen_inline_result()
async def chosen_result_handler(result: ChosenInlineResult, bot: Bot, db: AsyncSession, bot_data: BotData):
    inline_message_id = result.inline_message_id
    if not inline_message_id:
        return

    parts = result.result_id.split(":")
    if len(parts) != 2:
        return

    song_id = parts[1]
    res = await db.execute(select(Music).filter(Music.id == song_id))
    song = res.scalar_one_or_none()

    if not song:
        return

    inlines = Inlines(bot_data.texts)
    caption = bot_data.texts.song_music_caption.replace("<song_id>", song.id)
    performer_str = ', '.join([artist['name'] for artist in song.artists])
    switch_markup = inlines.music_lyrics(None, only_switch=True)

    async with _song_lock(song_id):
        # Re-fetch inside lock — another coroutine may have just cached file_id
        await db.refresh(song)

        if song.file_id:
            # Already cached — swap the loading audio for the real song immediately
            try:
                await bot.edit_message_media(
                    inline_message_id=inline_message_id,
                    media=InputMediaAudio(media=song.file_id, caption=caption),
                    reply_markup=switch_markup,
                )
            except Exception as exc:
                logger.debug("Could not deliver cached song inline: %s", exc)
            return

        # Swap to a generic "Loading your song…" placeholder — no artist, no thumbnail —
        # while the real file downloads. This MUST be a fresh upload (FSInputFile), not a
        # reused existing file_id: Telegram only honors title/performer overrides on
        # edit_message_media when the media is freshly uploaded, not when reusing an
        # existing file_id. The placeholder mp3 is tiny, so this stays fast.
        try:
            await bot.edit_message_media(
                inline_message_id=inline_message_id,
                media=InputMediaAudio(
                    media=FSInputFile(config.LOADING_SONG_LOCAL_PATH),
                    caption=bot_data.texts.song_loading,
                    title="🎵 Loading your song…",
                    performer=None,
                ),
                reply_markup=switch_markup,
            )
        except Exception as exc:
            logger.debug("Could not show loading placeholder inline: %s", exc)
            await _edit_inline_error(bot, inline_message_id, bot_data.texts.song_loading, switch_markup)

        try:
            file_path = await HandlersHelper.music_download(song)
        except Exception as exc:
            logger.exception("Download failed for song %s: %s", song_id, exc)
            await _edit_inline_error(
                bot, inline_message_id, f"❌ {bot_data.texts.not_found}", switch_markup
            )
            return

        # Telegram/aiogram cannot upload a fresh local file straight into an inline
        # message — send it privately once to mint a permanent file_id, then edit inline.
        try:
            try:
                private_msg = await bot.send_audio(
                    result.from_user.id,
                    audio=FSInputFile(file_path),
                    title=song.title,
                    performer=performer_str,
                    thumbnail=URLInputFile(song.photo),
                )
            except (TelegramForbiddenError, TelegramBadRequest) as exc:
                logger.warning("Cannot reach user %s to mint file_id: %s", result.from_user.id, exc)
                await _edit_inline_error(
                    bot, inline_message_id,
                    f"🎵 {song.title} — {performer_str}\n"
                    "⚠️ Start a private chat with the bot, then try again.",
                    switch_markup,
                )
                return
        finally:
            # The local copy is no longer needed once we've either uploaded it or
            # given up — never let it linger on disk.
            if os.path.exists(file_path):
                os.remove(file_path)

        file_id = private_msg.audio.file_id
        try:
            await private_msg.delete()
        except Exception:
            pass

        song.file_id = file_id
        await db.commit()

        try:
            await bot.edit_message_media(
                inline_message_id=inline_message_id,
                media=InputMediaAudio(media=file_id, caption=caption),
                reply_markup=switch_markup,
            )
        except Exception as exc:
            logger.warning("Could not replace inline loading audio with real song: %s", exc)
