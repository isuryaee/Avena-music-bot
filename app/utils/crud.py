from aiogram import Bot
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from aiogram.types import User, Chat

from app.models import (
    User as UserModel,
    Chat as ChatModel
)


async def get_user(info: User, db: AsyncSession) -> UserModel:
    user_query = await db.execute(
        select(UserModel)
        .where(UserModel.id == info.id)
    )
    user = user_query.scalars().first()

    if not user:
        user = UserModel(id=info.id, info=info.model_dump(mode="json", exclude_none=True))
        db.add(user)    
        await db.commit()

    return user


async def get_chat(chat_data: Chat, db: AsyncSession, bot: Bot = None, default_lang="en") -> ChatModel:
    chat_query = await db.execute(
        select(ChatModel)
        .where(ChatModel.id == chat_data.id)
    )
    chat = chat_query.scalars().first()

    if not chat:
        admins = await bot.get_chat_administrators(chat_data.id)
        admin_list = [admin.user.id for admin in admins]
        
        chat = ChatModel(id=chat_data.id, 
                         info=chat_data.model_dump(mode="json", exclude_none=True), 
                         lang=default_lang,
                         admins=admin_list)
        db.add(chat)
        await db.commit()

    return chat
