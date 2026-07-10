import os
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

class Config:
    DATABASE_URL = os.getenv("BOT_DATABASE_URL")
    SECRET = os.getenv("SECRET")
    TOKEN = os.getenv("TOKEN")

    # Control whether to allow downloading from generic/less popular sources
    IS_GENERIC_URL_OK = False

    # File size limits (in MB) - set to 0 to disable
    DOWNLOAD_VIDEO_SIZE_IN_MB = 20  # Max 20MB
    DOWNLOAD_VOICE_SIZE_IN_MB = 5
    DOWNLOAD_URL_SIZE_IN_MB = 40

    # Telegram API configurations
    BASE = "api.telegram.org"
    WEBHOOK_URL = ""  # Example: https://yourdomain.com/webhook
    WEBHOOK_PATH = ""  # Example: /webhook

    # Placeholder audio file for loading state (original URL kept as fallback)
    LOADING_SONG = "https://s3.filebin.net/filebin/c08376ec0ac682f9575943f68e78dcf61f5a9c9d6b3bc9f9ccb3420a72a53f63/0f0217efbd0328b4c312f8bc31ffe13449d5f3bd401ed2533c3b56e7199b8f6f?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=7pMj6hGeoKewqmMQILjm%2F20250328%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250328T233625Z&X-Amz-Expires=60&X-Amz-SignedHeaders=host&response-cache-control=max-age%3D60&response-content-disposition=filename%3D%22clear-silent-track.mp3%22&response-content-type=audio%2Fmpeg&X-Amz-Signature=dbefa68d24d1295f89e235e9b79ac43ab0706f53540a7a88a3a800e2b7848446"

    # Public URL for a small silent/placeholder mp3, used as the `audio_url` for
    # InlineQueryResultAudio inline-search rows. Unlike InlineQueryResultCachedAudio,
    # this result type lets us set an explicit title/performer per row, so the search
    # list shows the real song name immediately instead of "Loading...".
    # Override via LOADING_SONG_URL env var (required once this bot moves off Replit,
    # since it otherwise points at this workspace's sibling API server).
    _loading_song_url_env = os.getenv("LOADING_SONG_URL")
    if _loading_song_url_env:
        LOADING_SONG_URL = _loading_song_url_env
    else:
        _replit_domain = os.getenv("REPLIT_DEV_DOMAIN") or (os.getenv("REPLIT_DOMAINS", "").split(",")[0] or None)
        LOADING_SONG_URL = f"https://{_replit_domain}/api/loading-song.mp3" if _replit_domain else LOADING_SONG

    # Local path to the small placeholder mp3 used for fresh re-uploads (see inline.py).
    # A *fresh* upload (unlike reusing an existing file_id) lets Telegram honor an
    # explicit title/performer override on edit_message_media.
    LOADING_SONG_LOCAL_PATH = os.path.join(os.path.dirname(__file__), "..", "loading_song.mp3")

    # Cached Telegram file_id for the loading song — populated on first normal download.
    # Stored in loading_song_file_id.txt next to this file so it survives restarts.
    _LOADING_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "loading_song_file_id.txt")
    try:
        with open(_LOADING_CACHE_PATH) as _f:
            LOADING_SONG_FILE_ID: str | None = _f.read().strip() or None
    except FileNotFoundError:
        LOADING_SONG_FILE_ID: str | None = None

    @classmethod
    def save_loading_file_id(cls, file_id: str):
        """Persist the loading-song file_id so inline mode can use it."""
        cls.LOADING_SONG_FILE_ID = file_id
        try:
            with open(cls._LOADING_CACHE_PATH, "w") as f:
                f.write(file_id)
        except Exception:
            pass

    @classmethod
    def clear_loading_file_id(cls):
        """Drop a cached loading file_id that Telegram no longer recognizes."""
        cls.LOADING_SONG_FILE_ID = None
        try:
            os.remove(cls._LOADING_CACHE_PATH)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # Path for storing YouTube cookies — place cookies.txt in bot/ folder
    _cookies_env = os.getenv("COOKIES_PATH")
    _cookies_default = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt")
    COOKIES_PATH = _cookies_env if _cookies_env else (_cookies_default if os.path.exists(_cookies_default) else None)

    # Telegram Admin User ID (for bot management)
    ADMIN = 1000000  # Replace with actual admin ID

    # Load default bot response texts from JSON
    with open(os.path.join("app", "data", "default_texts.json")) as f:
        DEFAULT_TEXTS = json.load(f)

config = Config()
