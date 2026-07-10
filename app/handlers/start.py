from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.keyboards.inline import Inlines
from app.utils.helpers import HandlersHelper
from app.utils.states import MusicRecognition
from app.utils.bot_data import BotData
from app.filters import DynamicBotDataFilter, GroupFilter

router = Router()

@router.message(GroupFilter(), Command("start"))
async def group_start_handler(message: Message, bot_data: BotData,  bot: Bot):
    helper = HandlersHelper(message, bot_data, bot)
    await helper.send_start(bot_data.texts.chat_welcome)

@router.message(Command("start"))
@router.message(Command("lang"))
async def start_handler(message: Message):
    inlines = Inlines(None)
    
    await message.answer("👋")
    await message.answer("🌍🌎🌏🌍🌎🌏", reply_markup=inlines.lang(), 
                         message_effect_id="5104841245755180586")

@router.message(DynamicBotDataFilter("back"))
async def lang_query(
    message: Message, bot_data: BotData,
    bot: Bot, state: FSMContext
):
    await state.set_state(MusicRecognition.search)
    
    helper = HandlersHelper(message, bot_data, bot)
    await helper.send_start()
