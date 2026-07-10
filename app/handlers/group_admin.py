from aiogram import Router, Bot
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import GroupFilter
from app.keyboards.inline import Inlines
from app.models import Chat
from app.utils.bot_data import BotData


router = Router()


@router.message(GroupFilter(), lambda m: m.text and m.text.startswith("/admin"))
async def group_admin(message: Message, bot_data: BotData, chat: Chat):
    user_id = message.from_user.id
    
    if user_id not in chat.admins:
        if not chat.data.get("quiet"):
            await message.answer(bot_data.texts.not_admin)
            
        try:
            await message.delete()
        finally:
            return
    
    inlines = Inlines(bot_data.texts)
    settings = chat.data
    
    keyboard = inlines.group_admin(settings)
    await message.answer(bot_data.texts.group_admin_message, reply_markup=keyboard)
    
    try:
        await message.delete()
    except:
        pass
    

@router.callback_query(GroupFilter(), lambda c: c.data == "group_lang")
async def group_lang(callback_query: CallbackQuery, bot_data: BotData, chat: Chat):
    user_id = callback_query.from_user.id
    if user_id not in chat.admins:
        return await callback_query.answer(bot_data.texts.not_admin)
    
    inlines = Inlines(bot_data.texts)
    keyboard = inlines.lang()
    await callback_query.message.edit_text("🌍🌎🌏🌍🌎🌏", reply_markup=keyboard)
    
    
@router.callback_query(GroupFilter(), lambda c: c.data.startswith("group-"))
async def group_alltexts(
    callback_query: CallbackQuery, bot_data: BotData,
    db: AsyncSession, chat: Chat
):
    user_id = callback_query.from_user.id
    
    if user_id not in chat.admins:
        return await callback_query.answer(bot_data.texts.not_admin)
    
    inlines = Inlines(bot_data.texts)
    key = callback_query.data.split("-")[1]
    data = chat.data
    data[key] = not data.get(key, False)
    
    chat.data = data
    await db.commit()
    
    settings = chat.data
    keyboard = inlines.group_admin(settings)
    
    await callback_query.message.edit_text(bot_data.texts.group_admin_message, reply_markup=keyboard)
    

@router.callback_query(GroupFilter(), lambda c: c.data == "group_refresh")
async def group_alltexts(
    callback_query: CallbackQuery, bot_data: BotData,
    db: AsyncSession, bot: Bot, chat: Chat
):
    user_id = callback_query.from_user.id
    
    if user_id not in chat.admins:
        return await callback_query.answer(bot_data.texts.not_admin)
    
    chat_loaded = await bot.get_chat(chat.id)
    admins = await chat_loaded.get_administrators()
    admins_list = [admin.user.id for admin in admins]
    
    chat.info = chat_loaded.model_dump(mode="json", exclude_none=True)
    chat.admins = admins_list
    await db.commit()
    
    await callback_query.answer(bot_data.texts.done)


@router.callback_query(GroupFilter(), lambda c: c.data == "group_done")
async def group_alltexts(callback_query: CallbackQuery, bot_data: BotData, chat: Chat):
    user_id = callback_query.from_user.id
    
    if user_id not in chat.admins:
        return await callback_query.answer(bot_data.texts.not_admin)
    
    await callback_query.answer(bot_data.texts.done)
    await callback_query.message.delete()
