from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import GroupFilter
from app.keyboards.inline import Inlines
from app.models import Chat, User
from app.utils.bot_data import BotData
from app.utils.helpers import HandlersHelper
from app.utils.states import MusicRecognition
from app.config import config


router = Router()


@router.callback_query(GroupFilter(), lambda c: c.data.startswith("lang:"))
async def lang_chat_query(
    callback_query: CallbackQuery, bot_data: BotData, 
    db: AsyncSession, chat: Chat
):
    user_id = callback_query.from_user.id
    if user_id not in chat.admins:
        return await callback_query.answer(bot_data.texts.not_admin)
    
    lang = callback_query.data.split(":")[1]
    chat.lang = lang
    await db.commit()

    bot_data.texts.lang = lang
    
    inlines = Inlines(bot_data.texts)
    keyboard = inlines.group_admin(chat.data)
    await callback_query.answer(bot_data.texts.done)
    await callback_query.message.edit_text(bot_data.texts.group_admin_message, reply_markup=keyboard)


@router.callback_query(lambda c: c.data.startswith("lang:"))
async def lang_query(
    callback_query: CallbackQuery, bot_data: BotData, db: AsyncSession, 
    user: User, bot: Bot, state: FSMContext
):
    lang = callback_query.data.split(":")[1]
    user.lang = lang
    await db.commit()

    bot_data.texts.lang = lang
    await state.set_state(MusicRecognition.search)
    
    helper = HandlersHelper(callback_query, bot_data, bot)
    await helper.send_start(bot_data.texts.welcome)
    if callback_query.from_user.id == config.ADMIN:
        await callback_query.message.answer(bot_data.texts.admin_command)
    
    await callback_query.message.delete()


@router.callback_query(GroupFilter(), lambda c: c.data.startswith("song:"))
async def song_query(
    callback_query: CallbackQuery, bot_data: BotData, 
    db: AsyncSession, bot: Bot, chat: Chat
):
    quiet = chat.data.get("quiet")
    if quiet:
        await callback_query.message.delete()
        
    song_id = callback_query.data.split(":")[1]
    
    helper = HandlersHelper(callback_query, bot_data, bot, db)
    await helper.send_music_data(song_id, quiet)


@router.callback_query(lambda c: c.data.startswith("song:"))
async def song_query(
    callback_query: CallbackQuery, bot_data: BotData, 
    db: AsyncSession, bot: Bot
):
    song_id = callback_query.data.split(":")[1]
    
    helper = HandlersHelper(callback_query, bot_data, bot, db)
    await helper.send_music_data(song_id)


@router.callback_query(lambda c: c.data.startswith("search:"))
async def music_search(
    callback_query: CallbackQuery, bot_data: BotData, 
    db: AsyncSession, bot: Bot
):
    parts = callback_query.data.split(":")
    offset = int(parts[1])
    
    keyboards = callback_query.message.reply_markup.inline_keyboard
    via_btn = keyboards[-1][0]

    result_text = via_btn.switch_inline_query_current_chat
    
    helper = HandlersHelper(callback_query, bot_data, bot, db)
    await helper.send_search(result_text, offset)


@router.callback_query(lambda c: c.data.startswith("download:"))
async def download_query(
    callback_query: CallbackQuery, bot_data: BotData, 
    db: AsyncSession
):
    helper = HandlersHelper(callback_query, bot_data, None, db)
    await helper.download_song()


@router.callback_query(lambda c: c.data.startswith("lyrics:"))
async def lyrics_query(
    callback_query: CallbackQuery, bot_data: BotData, 
    db: AsyncSession
):  
    song_id = callback_query.data.split(":")[1]
    helper = HandlersHelper(callback_query, bot_data, None, db)
    parts = await helper.lyrics_maker(song_id)
    if not parts:
        return
    
    for part in parts:
        await callback_query.message.reply(f"{part}\n\n{bot_data.texts.song_botname}")
