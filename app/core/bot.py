from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.telegram import TelegramAPIServer
from app.config import config

bot_session = AiohttpSession()
bot_session.api = TelegramAPIServer(base=f"https://{config.BASE}" + "/bot{token}/{method}", 
                                    file=f"https://{config.BASE}" + "/file/bot{token}/{path}")

default_properties = DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
bot = Bot(token=config.TOKEN, session=bot_session, default=default_properties)
