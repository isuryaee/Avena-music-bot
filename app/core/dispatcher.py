from aiogram import Dispatcher
from app.database import SessionLocal
from app.middlewares import DatabaseSessionMiddleware, ChatOrUserMiddleware
from app.utils.state import PostgresStorage

dp = Dispatcher(storage=PostgresStorage(SessionLocal))
dp.update.middleware(DatabaseSessionMiddleware(SessionLocal))
dp.update.middleware(ChatOrUserMiddleware())
