import glob
import tempfile
import time
import urllib.parse
import ffmpeg
from shazamio import Shazam
import yt_dlp
import httpx
import asyncio
import os
import eyed3
from functools import partial
from ytmusicapi import YTMusic

from app.config import config

os.makedirs("songs", exist_ok=True)
os.makedirs("user_files", exist_ok=True)

# Reused across calls instead of constructing a fresh client (and re-reading its
# local context) on every single search — shaves a bit of latency off inline search.
_ytmusic = YTMusic()

# ---------------------------------------------------------------------------
# JioSaavn — primary source (320kbps MP3, free, no auth, any IP, fast CDN)
# ---------------------------------------------------------------------------

_SAAVN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.jiosaavn.com/",
}

def _saavn_search_and_url(query: str) -> str | None:
    """Return a 320kbps CDN URL for `query`, or None if not found."""
    q = urllib.parse.quote(query)
    try:
        r = httpx.get(
            f"https://www.jiosaavn.com/api.php"
            f"?__call=search.getResults&q={q}&p=1&n=1&_format=json&_marker=0",
            headers=_SAAVN_HEADERS, timeout=15,
        )
        results = r.json().get("results", [])
        if not results:
            return None
        enc = results[0].get("encrypted_media_url", "")
        if not enc:
            return None

        r2 = httpx.get(
            f"https://www.jiosaavn.com/api.php"
            f"?__call=song.generateAuthToken"
            f"&url={urllib.parse.quote(enc)}&bitrate=320"
            f"&api_version=4&_format=json&ctx=web6dot0&_marker=0",
            headers=_SAAVN_HEADERS, timeout=15,
        )
        return r2.json().get("auth_url") or None
    except Exception:
        return None


def _saavn_download(query: str, out_path: str) -> bool:
    """Download from JioSaavn. Returns True on success."""
    cdn_url = _saavn_search_and_url(query)
    if not cdn_url:
        return False
    try:
        with httpx.stream("GET", cdn_url, headers=_SAAVN_HEADERS,
                          timeout=120, follow_redirects=True) as resp:
            if resp.status_code != 200:
                return False
            with open(out_path, "wb") as f:
                for chunk in resp.iter_bytes(65536):
                    f.write(chunk)
        return os.path.getsize(out_path) > 10_000
    except Exception:
        return False


# ---------------------------------------------------------------------------
# SoundCloud — secondary source (yt-dlp, no auth, any IP)
# ---------------------------------------------------------------------------

def _sc_search_url(query: str) -> str | None:
    """Two-step SC search: flat extract → real webpage_url."""
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                "extract_flat": True}) as ydl:
            r = ydl.extract_info(f"scsearch1:{query}", download=False)
        entries = r.get("entries") or []
        if entries and entries[0].get("webpage_url"):
            return entries[0]["webpage_url"]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# YtDownload — orchestrates all sources
# ---------------------------------------------------------------------------

class YtDownload:
    def __init__(self, data: dict):
        self.data = data
        name = data["title"].replace("/", "-").replace(" ", "_").replace(".", "").lower()
        self._base = f"songs/{name}_{int(time.time())}"
        self.path = self._base + ".m4a"

    def _find_file(self) -> str | None:
        matches = [f for f in glob.glob(self._base + ".*")
                   if not f.endswith((".part", ".ytdl"))]
        return matches[0] if matches else None

    def _ydl_opts(self, extra: dict | None = None) -> dict:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": self._base + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "noprogress": True,
            "nopart": True,
        }
        if extra:
            opts.update(extra)
        return opts

    def _yt_opts(self) -> dict:
        opts = self._ydl_opts({
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "extractor_args": {
                "youtube": {"player_client": ["tv_embedded", "ios", "mweb"]}
            },
        })
        if config.COOKIES_PATH:
            opts["cookiefile"] = config.COOKIES_PATH
        return opts

    async def download_audio_from_id(self, video_id: str):
        loop = asyncio.get_running_loop()

        artists = self.data.get("artist", [])
        artist_str = ", ".join(artists) if isinstance(artists, list) else str(artists)
        query = f"{self.data['title']} {artist_str}"

        # ── 1. JioSaavn (320kbps MP3, no auth, fast CDN) ────────────────────
        saavn_path = self._base + ".mp4"
        ok = await loop.run_in_executor(None, _saavn_download, query, saavn_path)
        if ok:
            self.path = saavn_path
            return

        # ── 2. SoundCloud (yt-dlp, no auth) ─────────────────────────────────
        try:
            sc_url = await loop.run_in_executor(None, _sc_search_url, query)
            if sc_url:
                with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
                    await loop.run_in_executor(None, partial(ydl.download, [sc_url]))
                found = self._find_file()
                if found:
                    self.path = found
                    return
        except Exception:
            pass

        # ── 3. YouTube tv_embedded (last resort) ─────────────────────────────
        with yt_dlp.YoutubeDL(self._yt_opts()) as ydl:
            await loop.run_in_executor(
                None, partial(ydl.download,
                              [f"https://www.youtube.com/watch?v={video_id}"])
            )
        found = self._find_file()
        if found:
            self.path = found

    # ── URL downloads (user pastes a link) ───────────────────────────────────

    @staticmethod
    def is_supported(url: str) -> bool:
        if config.IS_GENERIC_URL_OK:
            return True
        for e in yt_dlp.extractor.gen_extractors():
            if e.suitable(url) and e.IE_NAME != "generic":
                return True
        return False

    @staticmethod
    async def download_audio_from_url(url: str, path: str):
        if not YtDownload.is_supported(url) or config.DOWNLOAD_URL_SIZE_IN_MB == 0:
            return None
        loop = asyncio.get_running_loop()
        base = path.rsplit(".", 1)[0]
        opts = {
            "format": "bestaudio/best",
            "outtmpl": base + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "max_filesize": config.DOWNLOAD_URL_SIZE_IN_MB * 1024 * 1024,
            "postprocessors": [{"key": "FFmpegExtractAudio",
                                "preferredcodec": "m4a", "preferredquality": "192"}],
        }
        if config.COOKIES_PATH:
            opts["cookiefile"] = config.COOKIES_PATH
        with yt_dlp.YoutubeDL(opts) as ydl:
            await loop.run_in_executor(None, partial(ydl.download, [url]))
        matches = [f for f in glob.glob(base + ".*")
                   if not f.endswith((".part", ".ytdl"))]
        return matches[0] if matches else None

    def get(self):
        return open(self.path, "rb")

    def remove(self):
        if os.path.exists(self.path):
            os.remove(self.path)


# ---------------------------------------------------------------------------
# Song — Shazam recognition + YTMusic search
# ---------------------------------------------------------------------------

class Song:
    @staticmethod
    async def extract_audio_from_video(video_path: str, delete=True) -> str:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        await asyncio.to_thread(
            lambda: ffmpeg.input(video_path)
            .output(tmp_path, format="mp3", acodec="mp3", audio_bitrate="128k")
            .run(overwrite_output=True, quiet=True)
        )
        if delete:
            os.remove(video_path)
        return tmp_path

    @staticmethod
    async def recognize(file_path: str, delete=True):
        shazam = Shazam()
        result = await shazam.recognize(file_path)
        if delete:
            os.remove(file_path)
        return result

    @staticmethod
    async def search(query: str, limit=10, offset=0):
        loop = asyncio.get_running_loop()
        if offset > 5:
            offset = 5
        adjusted_limit = limit * (offset + 1)
        results = await loop.run_in_executor(
            None, _ytmusic.search, query, "songs", None, adjusted_limit)
        if not results:
            return [], False
        filtered = results[offset * limit:(offset + 1) * limit]
        video_ids = [s for s in filtered
                     if "videoId" in s and s["duration_seconds"] < 700]
        has_more = len(results) >= adjusted_limit and offset < 4
        return video_ids, has_more

    @staticmethod
    async def get(song: str):
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _ytmusic.search, song, "songs")
        return results[0] if results else None

    @staticmethod
    async def get_lyrics(song_id: str):
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _ytmusic.get_watch_playlist, song_id)
        if not info.get("lyrics"):
            return None
        result = await loop.run_in_executor(None, _ytmusic.get_lyrics, info["lyrics"])
        return result.get("lyrics")
