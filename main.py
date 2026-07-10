import asyncio
import argparse
import time
from aiohttp import web
from aiogram.types import FSInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from sqlalchemy import text

from app.handlers import register_bot_routes
from app.core.bot import bot
from app.core.dispatcher import dp
from app.config import config
from app.models import Base
from app.database import engine
from app.logger import *
import os

# Directories where downloaded/temp song files land. Every download path is meant
# to clean up after itself (see app/utils/helpers.py, app/handlers/inline.py), but
# this sweeper is a safety net for anything left behind by crashes, timeouts, or
# code paths we haven't audited yet — so disk usage never grows unbounded.
_TEMP_DIRS = ["songs", "user_files"]
_MAX_FILE_AGE_SECONDS = 10 * 60  # 10 minutes
_SWEEP_INTERVAL_SECONDS = 5 * 60  # 5 minutes


async def _sweep_temp_files_forever():
    while True:
        try:
            now = time.time()
            for directory in _TEMP_DIRS:
                if not os.path.isdir(directory):
                    continue
                for name in os.listdir(directory):
                    path = os.path.join(directory, name)
                    try:
                        if os.path.isfile(path) and now - os.path.getmtime(path) > _MAX_FILE_AGE_SECONDS:
                            os.remove(path)
                            print(f"🧹 Removed stale temp file: {path}")
                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        print(f"⚠️  Could not clean up {path}: {e}")
        except Exception as e:
            print(f"⚠️  Temp file sweep failed: {e}")
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)


async def _bootstrap_loading_song():
    """
    Upload loading_song.mp3 to Telegram once to get a permanent file_id.
    Sends to the first DB user (usually the admin), then deletes the message.
    Skipped if file_id is already cached in loading_song_file_id.txt.
    """
    if config.LOADING_SONG_FILE_ID:
        print("✅ Loading song file_id already cached.")
        return

    # Find a user to send to
    user_id = None
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1"))
            row = r.fetchone()
            if row:
                user_id = int(row[0])
    except Exception:
        pass

    if not user_id:
        print("⚠️  No users in DB yet — loading song file_id will be cached on first normal download.")
        return

    mp3_path = os.path.join(os.path.dirname(__file__), "loading_song.mp3")
    if not os.path.exists(mp3_path):
        print("⚠️  loading_song.mp3 not found — skipping bootstrap.")
        return

    try:
        msg = await bot.send_audio(
            user_id,
            audio=FSInputFile(mp3_path),
            title="🎵 Loading your song…",
            performer=None,
        )
        config.save_loading_file_id(msg.audio.file_id)
        await msg.delete()
        print(f"✅ Loading song bootstrapped and file_id cached.")
    except Exception as e:
        print(f"⚠️  Could not bootstrap loading song: {e}")
        print("   Inline mode will fall back to Article view until first normal download.")


async def start_polling(info):
    dp["bot_info"] = info
    await register_bot_routes(dp)
    await _bootstrap_loading_song()
    asyncio.create_task(_sweep_temp_files_forever())
    print("✅ Bot is running in polling mode...")
    await dp.start_polling(bot)


async def start_webhook(info, port):
    async def on_startup(app):
        await bot.set_webhook(config.WEBHOOK_URL, secret_token=config.SECRET)
        await _bootstrap_loading_song()
        asyncio.create_task(_sweep_temp_files_forever())

    async def on_shutdown(app):
        await bot.delete_webhook()

    dp["bot_info"] = info
    await register_bot_routes(dp)

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.SECRET).register(app, path=config.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    print("✅ Bot is running in webhook mode...")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    await asyncio.Event().wait()


async def main(mode: str, port: int = 8000):
    print("Checking database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot_info = await bot.get_me()

    if mode == "polling":
        await start_polling(bot_info)
    elif mode == "webhook":
        await start_webhook(bot_info, port)
    else:
        print("❌ Invalid mode! Use 'polling' or 'webhook'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the bot in polling or webhook mode.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-p", "--polling", action="store_true", help="Run the bot in polling mode")
    group.add_argument("-w", "--webhook", action="store_true", help="Run the bot in webhook mode")
    parser.add_argument("--port", type=int, default=8000, help="Port number for webhook mode (default: 8000)")

    args = parser.parse_args()
    mode = "polling" if args.polling else "webhook"
    asyncio.run(main(mode, args.port))
