import re
from aiogram import Router, Bot
from aiogram.types import Message
from sqlalchemy.dialects.postgresql import insert
from aiogram.filters.state import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import GroupFilter
from app.models import Chat
from app.utils.bot_data import BotData
from app.utils.crud import get_chat
from app.utils.states import MusicRecognition
from app.utils.helpers import HandlersHelper


router = Router()


@router.message(
    GroupFilter(),
    lambda m: m.reply_to_message and 
              (m.reply_to_message.video or m.reply_to_message.audio or\
                  m.reply_to_message.voice or m.reply_to_message.video_note) and 
              (m.text == '//' or m.text == "/search")
)
async def group_media_reply_process(
    message: Message, bot_data: BotData,
    db: AsyncSession, bot: Bot
):
    try:
        await message.delete()
    except:
        pass
    
    media = message.reply_to_message
    media_type = media.video or media.audio or media.voice or media.video_note
    if media_type:
        await HandlersHelper(
            media, bot_data, bot, db
        ).process_media(media_type)


@router.message(
    GroupFilter(),
    lambda m: (
        m.video or m.audio or m.voice or m.video_note
    ) and not m.via_bot
)
async def group_media_auto_process(
    message: Message, bot_data: BotData,
    db: AsyncSession, bot: Bot, chat: Chat
):
    media_type = message.video or message.audio or message.voice or message.video_note
    
    if not chat.data.get("all_media") and \
        (hasattr(media_type, "caption") and media_type.caption) not in ["/search", "//"]:
        return
    
    if media_type:
        await HandlersHelper(
            message, bot_data, bot, db
        ).process_media(media_type)
        
    
@router.message(GroupFilter(), lambda m: m.text and not m.via_bot)
async def group_text_search(
    message: Message, bot_data: BotData,
    db: AsyncSession, bot: Bot, chat: Chat
):
    text = message.text.strip()
    
    match = re.match(r"(/[\w]+|//)(@[\w]+)?\s*(.*)", text)
    if match:
        if not (text.startswith("/search") or text.startswith("//")):
            return
        
        query = match.group(3).strip()
    else:
        if not chat.data.get("all_texts"):
            return
        
        query = text

    if not query:
        if not chat.data.get("queit"):
            await message.reply(bot_data.texts.empty_term)
            
        return

    helper = HandlersHelper(message, bot_data, bot, db)
    if helper.is_valid_url(query):
        return await helper.url_handler(query, message.from_user.id)
    
    if len(query) > 300:
        return await message.answer(bot_data.texts.long)
    
    await helper.send_search(query)


@router.message(StateFilter(MusicRecognition.search), lambda m: m.text and not m.via_bot)
async def music_search(
    message: Message, bot_data: BotData, 
    db: AsyncSession, bot: Bot
):
    text = message.text
    helper = HandlersHelper(message, bot_data, bot, db)
    if helper.is_valid_url(text):
        return await helper.url_handler(text, message.from_user.id)
    
    if len(text) > 300:
        return await message.answer(bot_data.texts.long)
    
    await helper.send_search(text)


@router.message(StateFilter(MusicRecognition.search), lambda m: m.video and not m.via_bot)
async def music_search_video(message: Message, bot_data: BotData, db: AsyncSession, bot: Bot):
    helper = HandlersHelper(message, bot_data, bot, db)
    return await helper.process_media(message.video)


@router.message(StateFilter(MusicRecognition.search), lambda m: m.voice and not m.via_bot)
async def music_search_voice(message: Message, bot_data: BotData, db: AsyncSession, bot: Bot):
    helper = HandlersHelper(message, bot_data, bot, db)
    return await helper.process_media(message.voice)


@router.message(StateFilter(MusicRecognition.search), lambda m: m.audio and not m.via_bot)
async def music_search_audio(message: Message, bot_data: BotData, db: AsyncSession, bot: Bot):
    helper = HandlersHelper(message, bot_data, bot, db)
    return await helper.process_media(message.audio)


@router.message(StateFilter(MusicRecognition.search), lambda m: m.video_note and not m.via_bot)
async def music_search_video_note(message: Message, bot_data: BotData, db: AsyncSession, bot: Bot):
    helper = HandlersHelper(message, bot_data, bot, db)
    return await helper.process_media(message.video_note)


@router.message(lambda m: m.new_chat_members)
async def bot_added_handler(message: Message, bot: Bot, bot_data: BotData, db: AsyncSession):
    for member in message.new_chat_members:
        if member.id == bot.id:
            chat = message.chat
            if chat.type in ["group", "supergroup"]:
                admins = await bot.get_chat_administrators(chat.id)
                admin_list = [admin.user.id for admin in admins]

                stmt = insert(Chat).values(
                    id=chat.id, 
                    info=chat.model_dump(mode="json", exclude_none=True),
                    admins=admin_list
                ).on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "info": chat.model_dump(mode="json", exclude_none=True),
                        "admins": admin_list
                    }
                )
                
                await db.execute(stmt)
                await db.commit()
                
                await get_chat(chat, db, bot_data.id, bot_data.texts.lang)
                
                helper = HandlersHelper(message, bot_data, bot)
                await helper.send_start(bot_data.texts.chat_welcome)
