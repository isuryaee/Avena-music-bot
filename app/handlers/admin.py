import asyncio
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func

from app.keyboards.inline import Inlines
from app.models import Chat, Music, User
from app.utils.bot_data import BotData
from app.utils.states import MusicRecognition
from app.config import config

router = Router()


@router.message(Command("admin"))
async def admin_panel(message: Message, bot_data: BotData):
    if message.from_user.id != config.ADMIN or message.chat.type != "private":
        return
    
    inlines = Inlines(bot_data.texts)
    await message.answer(bot_data.texts.admin_menu, reply_markup=inlines.admin())
 
 
@router.callback_query(lambda c: c.data == "admin-back")
async def admin_back(callback_query: CallbackQuery, bot_data: BotData, state: FSMContext):
    if callback_query.from_user.id != config.ADMIN:
        return
    
    await state.set_state(MusicRecognition.search)
    
    inlines = Inlines(bot_data.texts)
    await callback_query.message.edit_text(bot_data.texts.admin_menu, reply_markup=inlines.admin())
    

@router.callback_query(lambda c: c.data == "admin-done")
async def admin_back(callback_query: CallbackQuery, bot_data: BotData):
    await callback_query.message.delete()
    await callback_query.answer(bot_data.texts.done)


@router.callback_query(lambda c: c.data == "admin-stat")
async def admin_stat(callback_query: CallbackQuery, bot_data: BotData, db: AsyncSession):
    if callback_query.from_user.id != config.ADMIN:
        return

    inlines = Inlines(bot_data.texts)
    stat_text = bot_data.texts.stat_text

    queries = [
        select(func.count(User.id)),
        select(func.count(Chat.id)),
        select(func.count(Music.id)),
        select(func.count(Music.id)).filter(Music.file_id != None)
    ]

    results = await asyncio.gather(*[db.execute(query) for query in queries])
    user_count, chat_count, music_count, sent_music_count = [str(result.scalar()) for result in results]

    stat_text = stat_text.replace("<all_users>", user_count)\
                         .replace("<all_groups>", chat_count)\
                         .replace("<music>", music_count)\
                         .replace("<music_sent>", sent_music_count)

    await callback_query.message.edit_text(stat_text, reply_markup=inlines.admin_back())
    

@router.callback_query(lambda c: c.data == "admin-broadcast")
async def admin_broadcast(callback_query: CallbackQuery, bot_data: BotData, state: FSMContext):
    if callback_query.from_user.id != config.ADMIN:
        return
    
    await state.set_state(MusicRecognition.broadcast)
    
    inlines = Inlines(bot_data.texts)
    await callback_query.message.edit_text(bot_data.texts.broadcast_message, reply_markup=inlines.admin_back())


@router.message(StateFilter(MusicRecognition.broadcast))
async def broadcast_handler(message: Message, bot_data: BotData, db: AsyncSession, state: FSMContext):
    if message.from_user.id != config.ADMIN or message.chat.type != "private":
        return
    
    msg = await message.answer(bot_data.texts.broadcasting)
    await state.set_state(MusicRecognition.search)

    sent_count = 0
    semaphore = asyncio.Semaphore(20)
    
    async def send_to_user(user_id):
        nonlocal sent_count
        async with semaphore:
            try:
                await message.copy_to(user_id)
                sent_count += 1
                if sent_count % 100 == 0:
                    await msg.edit_text(bot_data.texts.broadcast_count.replace("<sent_count>", str(sent_count)))
                    
                await asyncio.sleep(0.05)
                
            except Exception as e:
                print(f"Error sending to {user_id}: {e}")
    
    result = await db.execute(select(User.id))
    users = result.scalars().all()
    
    tasks = [send_to_user(user_id) for user_id in users]
    await asyncio.gather(*tasks)
    
    await msg.delete()
    await message.answer(bot_data.texts.broadcast_done.replace("<sent_count>", str(sent_count)))
