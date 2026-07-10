from aiogram.fsm.state import State, StatesGroup

class MusicRecognition(StatesGroup):
    search = State()
    broadcast = State()
