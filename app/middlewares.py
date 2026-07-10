from aiogram.types import TelegramObject, ChatMemberUpdated, Update
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Any, Dict, Callable, Awaitable
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.utils.bot_data import BotData
from app.utils.crud import get_chat, get_user


class DatabaseSessionMiddleware(BaseMiddleware):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker
        super().__init__()

    async def __call__(self, handler, event: Update, data: dict):
        async with self.session_maker() as session:
            data["db"] = session
            
            return await handler(event, data)


class ChatOrUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        bot = data["bot"]
        db = data.get("db")
        user = data.get("event_from_user")
        chat = data.get("event_chat")
        
        data["bot_data"] = BotData(data["bot_info"], user)
        
        if event.message and (
            event.message.new_chat_members or event.message.left_chat_member or\
                event.my_chat_member
        ):
            return await handler(event, data)
        
        if chat and chat.type in ["group", "supergroup"]:
            data["chat"] = await get_chat(chat, db, bot)
            data["bot_data"].texts.lang = data["chat"].lang
            
        elif user:
            data["user"] = await get_user(user, db)
            data["bot_data"].texts.lang = data["user"].lang
        
        return await handler(event, data)
    
