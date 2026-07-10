import asyncio
import hashlib
import os
import re
import secrets
import time
from typing import Union
import urllib.parse
from aiogram import Bot
import httpx
from sqlalchemy import select
from aiogram.types import (
    CallbackQuery, Message, VideoNote, Video, InlineQuery, FSInputFile, URLInputFile,
    InlineQueryResultArticle, InlineQueryResultCachedAudio, InlineQueryResultAudio,
    InputTextMessageContent, InputMediaAudio
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
import urllib

from app.keyboards.inline import Inlines
from app.logger import logger
from app.database import SessionLocal
from app.models import Music, User
from app.services.song_process import Song, YtDownload
from app.utils.bot_data import BotData
from app.config import config


client = httpx.AsyncClient(http2=True, timeout=1)


class MusicHelper:
    def __init__(self):
        pass
    
    @staticmethod
    def photo_resize(url: str, size: int = 300) -> str:
        url_parts = url.split('=')
        url_parts[1] = f"w{size}-h{size}"
        url = '='.join(url_parts)
        
        return url
    
    @staticmethod
    async def get_cover(url):
        async with httpx.AsyncClient() as client:
            cover_response = await client.get(MusicHelper.photo_resize(url, 100))
            cover_data = cover_response.content
            
            return cover_data
        
    @staticmethod
    async def get_musics_info(platforms, sign, song_id):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(headers=headers, timeout=10) as client:
            response = await client.get(f"https://song.link/{sign}/{song_id}")
            text = response.text
        
        extracted_links = {key: re.search(pattern, text) for key, pattern in platforms.items()}
        extracted_links = {
            key: match.group(1) if match and key in ["title", "artist"] else (match.group(0) if match else None)
            for key, match in extracted_links.items()
        }
        
        return extracted_links
    
    @staticmethod
    async def music_links(name: str, song_id: str) -> dict:
        default = {
            "youtube": f"https://www.youtube.com/watch?v={song_id}",
            "apple_music": f"https://music.apple.com/us/search?term={name}",
            "spotify": f"https://open.spotify.com/search/{name}",
            "soundcloud": f"https://soundcloud.com/search?q={name}",
        }

        platforms = {
            "youtube": r'https://www\.youtube\.com/watch\?v=[\w-]+',
            "apple_music": r'https://geo\.music\.apple\.com[^\s"]+',
            "spotify": r'https://open\.spotify\.com/track/[^\s"]+',
            "soundcloud": r'https://soundcloud\.com/[^\s"]+',
            "deezer": r'https://www\.deezer\.com/track/[^\s"]+',
            "audiomack": r'https://audiomack\.com/song/[^\s"]+',
        }
        
        try:
            extracted_links = await MusicHelper.get_musics_info(platforms, "y", song_id)
            return {"api": True, **extracted_links}

        except Exception as e:
            print(f"Error: {e}")

        return default
                
                
    @staticmethod
    async def get_song(song_id, db) -> Music:
        result = await db.execute(select(Music).filter(Music.file_id == song_id))
        song = result.scalar_one_or_none()
    
        return song


class HandlersHelper:
    def __init__(
        self, data: Union[CallbackQuery, Message], bot_data: BotData,
        bot: Bot, db: AsyncSession = None, user: User = None
    ):
        self.bot_data = bot_data
        self.texts = bot_data.texts
        self.data = data
        self.bot = bot
        self.db = db
        self.user = user
        
        
    @staticmethod
    def fullname_filter(text: str, song: Music):
        filters = {
            "<song_title>": song.title,
            "<song_artists>": ', '.join([artist['name'] for artist in song.artists])
        }
        
        for filter_, value in filters.items():
            text = text.replace(filter_, value)
            
        return text
    
    
    async def send_music_data(self, song_id: str, deleted=False):
        texts = self.texts
        inlines = Inlines(texts)
            
        chat_id = self.data.message.chat.id if isinstance(self.data, CallbackQuery) else self.data.chat.id
        if deleted:
            msg_id = None
        else:
            msg_id = self.data.message.message_id if isinstance(self.data, CallbackQuery) else self.data.message_id
        
        msg = await self.bot.send_message(chat_id, self.texts.load_icon, reply_to_message_id=msg_id)
        
        result = await self.db.execute(select(Music).filter(Music.id == song_id))
        song = result.scalar_one_or_none()
        
        if not song:
            return await self.bot.send_message(chat_id, texts.not_found, reply_to_message_id=msg_id)
            
        photo = song.photo
        full_name = self.fullname_filter(self.texts.song_fullname, song)
        caption = self.fullname_filter(self.texts.song_caption, song)
            
        if song.details:
            details = song.details
            
        else:
            details = await MusicHelper.music_links(full_name, song_id)
            song.details = details
            
            await self.db.commit()
            
        keyboard = inlines.music_data(
            song_id,
            full_name,
            details
        )
        
        await self.bot.send_photo(chat_id, photo, caption=caption, reply_markup=keyboard)
        await msg.delete()
        
    
    @staticmethod
    async def music_download(song):
        music_data = {
            "title": song.title,
            "artist": [artist["name"] for artist in song.artists],
            "album": song.album["name"],
            "photo": MusicHelper.photo_resize(song.photo, 200)
        }
        
        yt = YtDownload(music_data)
        
        await yt.download_audio_from_id(song.id)

        return yt.path
    
    
    @staticmethod
    def normalize_results(results):
        """Pure in-memory transform — no DB round trip — so callers on the hot path
        (e.g. answering an inline query) don't have to wait on a write first."""
        values = [
            {
                "id": result["videoId"],
                "title": result["title"],
                "artists": result["artists"],
                "album": result["album"],
                "photo": MusicHelper.photo_resize(result["thumbnails"][0]["url"])
            }
            for result in results
        ]

        return list({v["id"]: v for v in values}.values())

    @staticmethod
    async def write_results_to_db(values, db):
        if not values:
            return

        stmt = insert(Music).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=['id'],
            set_={
                "title": stmt.excluded.title,
                "artists": stmt.excluded.artists,
                "album": stmt.excluded.album,
                "photo": stmt.excluded.photo
            }
        )
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    async def add_result_in_db(results, db):
        values = HandlersHelper.normalize_results(results)
        await HandlersHelper.write_results_to_db(values, db)
        return values


    async def send_search(self, text: str, offset: int = 0):
        inlines = Inlines(self.texts)
        chat_id = self.data.message.chat.id if isinstance(self.data, CallbackQuery) else self.data.chat.id
        msg_id = self.data.message.message_id if isinstance(self.data, CallbackQuery) else self.data.message_id
        
        sent_msg = await self.bot.send_message(chat_id, self.texts.load_icon)
        song = Song()
        
        results, has_more = await song.search(text, offset=offset)
        if not results:
            await self.bot.send_message(chat_id, self.texts.not_found, reply_to_message_id=msg_id)
            await sent_msg.delete()
            return
            
        keyboard = inlines.music_search(results, self.bot_data.info.username, text, has_more, offset)
        
        await self.bot.send_message(chat_id, self.texts.results,
                            reply_to_message_id=msg_id, reply_markup=keyboard)
        await sent_msg.delete()
        
        await self.add_result_in_db(results, self.db)
        
    
    async def send_start(self, welcome):
        texts = self.texts
        inlines = Inlines(texts)
        
        chat_id = self.data.message.chat.id if isinstance(self.data, CallbackQuery) else self.data.chat.id
        await self.bot.send_message(chat_id, welcome, reply_markup=inlines.welcome(self.bot_data))

    
    @staticmethod
    async def download_file(bot: Bot, file_id: str, user_id: int):
        file_info = await bot.get_file(file_id)
        file_path = file_info.file_path
        
        os.makedirs("user_files", exist_ok=True)
        file_extension = 'dat'

        hashed_file_id = hashlib.sha256(file_id.encode()).hexdigest()[:16]
        file_name = f"{user_id}_{hashed_file_id}.{file_extension}"
        save_path = os.path.join("user_files", file_name)
        
        await bot.download_file(file_path, save_path)
        
        return save_path
    
    
    @staticmethod
    async def add_song_in_db(db, song):
        stmt = insert(Music).values(
            id=song["videoId"], 
            title=song["title"], 
            artists=song["artists"],
            album=song["album"],
            photo=MusicHelper.photo_resize(song["thumbnails"][0]["url"])
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "title": song["title"],
                "artists": song["artists"],
                "album": song["album"],
                "photo": MusicHelper.photo_resize(song["thumbnails"][0]["url"])
            }
        )
        
        await db.execute(stmt)
        await db.commit()
        
    
    @staticmethod
    async def recognize_file(path, db):
        found_song = await Song.recognize(path)
        if not found_song['matches']:
            return None
            
        full_name = f"{found_song['track']['title']} - {found_song['track']['subtitle']}"
        song = await Song.get(full_name)
        
        await HandlersHelper.add_song_in_db(db, song)
        return song["videoId"]
        

    async def process_media(self, media):
        file_id = media.file_id
        is_video = isinstance(media, Video) or isinstance(media, VideoNote)
        
        if is_video:
            limit = config.DOWNLOAD_VIDEO_SIZE_IN_MG
        else:
            limit = config.DOWNLOAD_VOICE_SIZE_IN_MG
            
        if not limit:
            return await self.data.reply(self.bot_data.texts.not_supported)
            
        if media.file_size > limit * 1024 * 1024:
            return await self.data.reply(self.bot_data.texts.big_file)
        
        msg = await self.data.reply(self.bot_data.texts.getting_file)
        file_path = await self.download_file(self.bot, file_id, self.data.from_user.id)
        
        if is_video:
            await msg.edit_text(self.bot_data.texts.working_on_file)
            file_path = await Song.extract_audio_from_video(file_path)
        
        await msg.edit_text(self.bot_data.texts.finding_music)
        song_id = await self.recognize_file(file_path, self.db)
        if not song_id:
            return await msg.edit_text(self.bot_data.texts.not_found)
        
        await msg.delete()
        await self.send_music_data(song_id)
        
    
    @staticmethod
    async def process_query(query: InlineQuery, bot_data: BotData, db: AsyncSession):
        text = query.query.strip()

        inlines = Inlines(bot_data.texts)
        song = Song()
        results, _ = await song.search(text)
        if not results:
            return await query.answer(
                [InlineQueryResultArticle(
                    id=secrets.token_hex(8),
                    title=bot_data.texts.not_found,
                    input_message_content=InputTextMessageContent(
                        message_text=bot_data.texts.not_found
                    ),
                    reply_markup=inlines.music_lyrics(None, only_switch=True)
                )],
                cache_time=0
            )

        # In-memory only — persisting to the DB is not needed to answer the query,
        # so it happens afterwards, off the hot path (see below).
        results = HandlersHelper.normalize_results(results)

        # Look up any songs already downloaded before (real per-file metadata, so we
        # can show them as genuinely cached audio — correct title, zero placeholder step).
        song_ids = [song["id"] for song in results]
        cached_rows = await db.execute(
            select(Music.id, Music.file_id).filter(Music.id.in_(song_ids), Music.file_id.isnot(None))
        )
        cached_file_ids = {row.id: row.file_id for row in cached_rows}

        audio_results = []
        for song in results:
            performer = ', '.join([artist['name'] for artist in song["artists"]])
            caption = f"🎵 {song['title']} — {performer}"
            markup = inlines.music_lyrics(None, only_switch=True)

            file_id = cached_file_ids.get(song["id"])
            if file_id:
                # Already downloaded before — this specific file's own metadata is
                # correct, so it displays properly in the list immediately.
                document = InlineQueryResultCachedAudio(
                    id=f"song:{song['id']}",
                    audio_file_id=file_id,
                    caption=caption,
                    reply_markup=markup
                )
            else:
                # Not cached yet: InlineQueryResultAudio (unlike the cached variant)
                # lets us set an explicit title/performer per row, so the real song
                # name shows immediately instead of a shared "Loading..." label.
                # The audio_url is only fetched by Telegram if/when this row is chosen.
                document = InlineQueryResultAudio(
                    id=f"song:{song['id']}",
                    audio_url=config.LOADING_SONG_URL,
                    title=song["title"],
                    performer=performer,
                    caption=caption,
                    reply_markup=markup
                )
            audio_results.append(document)

        await query.answer(audio_results, cache_time=0)

        # Persist the search results after answering — the request-scoped `db`
        # session is about to be closed by the middleware, so use a fresh one.
        asyncio.create_task(HandlersHelper._persist_results_safely(results))

    @staticmethod
    async def _persist_results_safely(values):
        try:
            async with SessionLocal() as bg_db:
                await HandlersHelper.write_results_to_db(values, bg_db)
        except Exception as exc:
            logger.debug("Background DB write for search results failed: %s", exc)
        
    @staticmethod
    def is_valid_url(text):
        pattern = r"^https://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$"
        return re.match(pattern, text)
    
    
    @staticmethod
    def extract_platform_and_id(url: str):
        patterns = [
            (r"https://music\.apple\.com/.*/album/.*/\d+\?i=(\d+)", "i"),
            (r"https://geo\.music\.apple\.com/.*/album/.*/\d+\?i=(\d+)", "i"),
            (r"https://open\.spotify\.com/track/([a-zA-Z0-9_-]+)", "s"),
            (r"https://www\.pandora\.com/track/([a-zA-Z0-9_-]+)", "p"),
            (r"https://www\.deezer\.com/.*/track/(\d+)", "d"),
            (r"https://soundcloud\.com/.*/([a-zA-Z0-9_-]+)", "sc"),
            (r"https://music\.amazon\..*/albums?/([A-Z0-9]+)", "a"),
            (r"https://tidal\.com/browse/track/(\d+)", "t"),
            (r"https://us\.napster\.com/track/([a-zA-Z0-9_-]+)", "n"),
            (r"https://music\.yandex\..*/album/\d+/track/(\d+)", "ya"),
            (r"https://audiomack\.com/.*/song/([a-zA-Z0-9_-]+)", "am"),
            (r"https://www\.boomplay\.com/songs/(\d+)", "bp"),
            (r"https://play\.anghami\.com/song/([a-zA-Z0-9_-]+)", "an")
        ]
        
        for pattern, platform in patterns:
            match = re.search(pattern, url)
            if match:
                return {
                    'platform': platform,
                    'id': match.group(1)
                }
                
        return None
    
    @staticmethod
    async def get_yt(song_id, platform):
        platforms = {
            "youtube": r'https://www\.youtube\.com/watch\?v=([\w-]+)',
            "apple_music": r'https://geo\.music\.apple\.com[^\s"]+',
            "spotify": r'https://open\.spotify\.com/track/[^\s"]+',
            "soundcloud": r'https://soundcloud\.com/[^\s"]+',
            "title": r'<div class="css-1oiqcyt e12n0mv61">(.*?)</div>',
            "artist": r'<div class="css-1vk2kj9 e12n0mv60">(.*?)</div>'
        }
        
        res = await MusicHelper.get_musics_info(platforms, platform, song_id)
        is_valid = True
        
        if not (res["apple_music"] or res["spotify"] or res["soundcloud"]):
            is_valid = False
        
        return f"{res['title']} - {res['artist']}", is_valid
    
    
    async def url_handler(self, text, user_id):
        link_data = self.extract_platform_and_id(text)
        if link_data:
            msg = await self.data.reply(self.texts.get_contents)
            yt_name, valid = await self.get_yt(link_data['id'], link_data['platform'])
            if not valid:
                await msg.delete()
                return await self.data.reply(self.texts.not_found)
            
            song = await Song.get(yt_name)
            await self.add_song_in_db(self.db, song)
            
            await msg.delete()
            return await self.send_music_data(song["videoId"])
        
        msg = await self.data.reply(self.texts.get_contents)
        
        path = f"user_files/{user_id}_{int(time.time())}.m4a"
        path = await YtDownload.download_audio_from_url(text, path)
        if path is None:
            return await msg.edit_text(self.texts.not_supported)
        
        if not os.path.exists(path):
            return await msg.edit_text(self.texts.unable)
        
        song_id = await self.recognize_file(path, self.db)
        if not song_id:
            return await msg.edit_text(self.texts.not_found)
        
        await msg.delete()
        await self.send_music_data(song_id)
        
    
    async def download_song(self):
        song_id = self.data.data.split(":")[1]
        result = await self.db.execute(select(Music).filter(Music.id == song_id))
        song = result.scalar_one_or_none()
        inlines = Inlines(self.bot_data.texts)
        
        if not song:
            return await self.data.answer(self.bot_data.texts.not_found)
        
        caption = self.bot_data.texts.song_music_caption.replace("<song_id>", song.id)
        
        if song.file_id:
            return await self.data.message.reply_audio(
                song.file_id,
                caption=caption, 
                reply_markup=inlines.music_lyrics(song_id)
            )
        
        keyboard = inlines.music_lyrics(song_id)
        sent_msg = await self.data.message.answer_audio(
            config.LOADING_SONG_FILE_ID or config.LOADING_SONG_URL,
            caption=self.bot_data.texts.song_loading,
            reply_markup=keyboard
        )

        # Cache Telegram file_id so inline mode can use it without re-fetching the URL
        if not config.LOADING_SONG_FILE_ID and sent_msg.audio:
            config.save_loading_file_id(sent_msg.audio.file_id)

        file_path = await self.music_download(song)

        try:
            msg = await sent_msg.edit_media(
                media=InputMediaAudio(
                    media=FSInputFile(file_path), caption=caption, title=song.title,
                    performer=', '.join([artist['name'] for artist in song.artists]),
                    thumbnail=URLInputFile(song.photo)
                ),
                reply_markup=keyboard
            )

            song.file_id = msg.audio.file_id
            await self.db.commit()
        finally:
            # The file is now stored on Telegram's side (file_id) — no need to keep
            # a local copy taking up disk space.
            if os.path.exists(file_path):
                os.remove(file_path)
        
        
    async def lyrics_maker(self, song_id):
        result = await self.db.execute(select(Music).filter(Music.id == song_id))
        song = result.scalar_one_or_none()
        
        if not song:
            await self.data.message.reply(self.bot_data.texts.not_found)
            return
        
        msg = await self.data.message.reply(self.bot_data.texts.load_icon)
        
        if song.lyrics:
            lyrics = song.lyrics
            
        else:
            lyrics = await Song.get_lyrics(song_id)
            song.lyrics = lyrics
            await self.db.commit()
        
        if not lyrics:
            await msg.edit_text(self.bot_data.texts.no_lyrics)
            return
        
        max_length = 4096
        parts = []
        while len(lyrics) > max_length:
            split_index = lyrics[:max_length].rfind('\n')
            if split_index == -1:
                split_index = max_length
            parts.append(lyrics[:split_index])
            lyrics = lyrics[split_index:].strip()
            
        parts.append(lyrics)
        await msg.delete()
        
        return parts
